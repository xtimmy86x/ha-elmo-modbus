"""Alarm control panel entities for the Elmo Modbus integration."""

from __future__ import annotations

from typing import Any, Iterable

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.components.alarm_control_panel.const import CodeFormat
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.config_validation import slugify
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymodbus.exceptions import ConnectionException

from .const import DEFAULT_SECTORS, DOMAIN, OPTION_USER_CODES, REGISTER_COMMAND_START
from .coordinator import (
    ElmoModbusCoordinator,
    ElmoModbusInventory,
    ElmoPanelStatus,
)
from .panels import MODES, PanelDefinition, load_panel_definitions

import logging
_LOGGER = logging.getLogger(__name__)

MODE_LABELS = {
    "away": "Arm Away",
    "home": "Arm Home",
    "night": "Arm Night",
}


STATE_PRIORITY = {
    AlarmControlPanelState.ARMED_AWAY: 3,
    AlarmControlPanelState.ARMED_NIGHT: 2,
    AlarmControlPanelState.ARMED_HOME: 1,
}

MODE_TO_STATE = {
    "away": AlarmControlPanelState.ARMED_AWAY,
    "home": AlarmControlPanelState.ARMED_HOME,
    "night": AlarmControlPanelState.ARMED_NIGHT,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the alarm control panel entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusCoordinator = data["coordinator"]
    inventory: ElmoModbusInventory = data["inventory"]
    inventory.require_status()

    panels = load_panel_definitions(entry.options, max_sector=coordinator.sector_count)
    entities = [
        ElmoModbusAlarmControlPanel(entry, coordinator, inventory, panel)
        for panel in panels
    ]

    if entities:
        async_add_entities(entities)


class ElmoModbusAlarmControlPanel(
    CoordinatorEntity[ElmoModbusCoordinator], AlarmControlPanelEntity
):
    """Representation of the Modbus-backed alarm panel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        inventory: ElmoModbusInventory,
        panel: PanelDefinition,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._panel = panel
        self._config_entry = entry
        self._host = entry.data["host"]
        self._port = entry.data["port"]
        self._inventory = inventory

        raw_codes = entry.options.get(OPTION_USER_CODES, [])
        if isinstance(raw_codes, list):
            self._user_codes = tuple(
                code.strip()
                for code in raw_codes
                if isinstance(code, str) and code.strip()
            )
        else:
            self._user_codes = tuple()
        self._attr_code_arm_required = bool(self._user_codes)

        self._attr_unique_id = f"{entry.entry_id}:{panel.slug}"
        self._attr_name = panel.name
        device_slug = slugify(entry.title)
        self.entity_id = f"alarm_control_panel.{device_slug}_{panel.slug}"

        self._mode_sectors: dict[str, set[int]] = {}
        for mode in MODES:
            sectors = panel.mode_sectors(mode)
            if sectors:
                self._mode_sectors[mode] = sectors

        self._managed_sectors = panel.managed_sectors

        supported = AlarmControlPanelEntityFeature(0)
        if "away" in self._mode_sectors:
            supported |= AlarmControlPanelEntityFeature.ARM_AWAY
        if "home" in self._mode_sectors:
            supported |= AlarmControlPanelEntityFeature.ARM_HOME
        if "night" in self._mode_sectors:
            supported |= AlarmControlPanelEntityFeature.ARM_NIGHT
        self._attr_supported_features = supported

    @property
    def _all_sectors(self) -> set[int]:
        """Return a set with all known sector numbers."""

        return {index + 1 for index in range(self.coordinator.sector_count)}

    def _require_valid_code(self, code: str | None) -> None:
        """Ensure the provided code is valid when codes are configured."""

        if not self._user_codes:
            return
        if code is None:
            raise HomeAssistantError(
                "A valid code is required to control this alarm panel."
            )
        if code not in self._user_codes:
            raise HomeAssistantError("Invalid code provided.")

    def _target_sectors(self, mode: str) -> set[int]:
        """Return the sectors that should be armed for a specific mode."""

        sectors = self._mode_sectors.get(mode)
        if sectors:
            return sectors
        raise HomeAssistantError(
            f"No sectors configured for {MODE_LABELS.get(mode, mode)}"
            f"on panel {self._panel.name}"
        )

    def _build_command_payload(
        self, target_sectors: Iterable[int], *, value: bool
    ) -> list[bool]:
        """Convert a sector iterable into a bit payload for the command coils."""

        snapshot = self.coordinator.data
        status: ElmoPanelStatus | None = snapshot.status if snapshot else None

        if status:
            payload = list(status.armed)
        else:
            span = max(1, min(self.coordinator.sector_count, DEFAULT_SECTORS))
            payload = [False] * span

        span = len(payload)

        if self._managed_sectors:
            scope = {sector for sector in self._managed_sectors if 1 <= sector <= span}
        else:
            scope = set(range(1, span + 1))

        targets = {
            sector
            for sector in target_sectors
            if 1 <= sector <= span and sector in scope
        }

        for sector in scope:
            payload[sector - 1] = value if sector in targets else False
        return payload

    async def _async_send_command(
        self, target_sectors: Iterable[int], *, value: bool
    ) -> None:
        """Send the Modbus command to set the desired arming state."""

        payload = self._build_command_payload(target_sectors, value=value)

        def _write() -> None:
            self._inventory.write_coils(REGISTER_COMMAND_START, payload)

        try:
            await self.hass.async_add_executor_job(_write)
        except ConnectionException as err:
            raise HomeAssistantError(
                f"Failed to send command to {self._host}:{self._port}"
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send a Modbus command to disarm the configured sectors."""

        self._require_valid_code(code)
        target = self._managed_sectors or self._all_sectors
        await self._async_send_command(target, value=False)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured away sectors."""

        self._require_valid_code(code)
        await self._async_send_command(self._target_sectors("away"), value=True)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured home sectors."""

        self._require_valid_code(code)
        await self._async_send_command(self._target_sectors("home"), value=True)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured night sectors."""

        self._require_valid_code(code)
        await self._async_send_command(self._target_sectors("night"), value=True)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the alarm panel."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name=self._config_entry.title,
        )

    @property
    def code_format(self) -> str | None:
        """Return the expected format for the configured codes."""

        if not self._user_codes:
            return None
        if all(code.isdigit() for code in self._user_codes):
            return CodeFormat.NUMBER
        return CodeFormat.TEXT

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current state of the alarm panel."""

        snapshot = self.coordinator.data
        if snapshot is None or snapshot.status is None:
            return None

        status = snapshot.status
        armed_bits = status.armed
        triggered_bits = status.triggered

        general_alarm = snapshot.discrete_inputs.get(0x0200)

        panel_armed, panel_triggered, panel_total = self._compute_panel_sectors(
            armed_bits, triggered_bits,
        )

        if panel_triggered and general_alarm:
            return AlarmControlPanelState.TRIGGERED

        if not panel_armed:
            return AlarmControlPanelState.DISARMED

        return self._resolve_armed_state(panel_armed, panel_total)

    def _compute_panel_sectors(
        self,
        armed_bits: tuple[bool, ...],
        triggered_bits: tuple[bool, ...],
    ) -> tuple[set[int], set[int], int]:
        """Derive armed/triggered sector sets scoped to this panel."""

        armed_all = {i + 1 for i, b in enumerate(armed_bits) if b}
        triggered_all = {i + 1 for i, b in enumerate(triggered_bits) if b}

        if self._managed_sectors:
            armed = armed_all & self._managed_sectors
            triggered = triggered_all & self._managed_sectors & armed
            total = len(self._managed_sectors)
        else:
            armed = armed_all
            triggered = triggered_all & armed
            total = len(armed_bits)

        return armed, triggered, total

    def _resolve_armed_state(
        self, panel_armed: set[int], panel_total: int,
    ) -> AlarmControlPanelState:
        """Match the armed sectors against configured mode profiles."""

        options_map: dict[AlarmControlPanelState, set[int]] = {
            MODE_TO_STATE[mode]: sectors
            for mode, sectors in self._mode_sectors.items()
        }

        # Armed-away takes priority: if all its sectors are active, match
        away_sectors = options_map.get(AlarmControlPanelState.ARMED_AWAY)
        if away_sectors and away_sectors <= panel_armed:
            return AlarmControlPanelState.ARMED_AWAY

        # Exact match for remaining modes
        for state, sectors in options_map.items():
            if state == AlarmControlPanelState.ARMED_AWAY:
                continue
            if panel_armed == sectors:
                return state

        # All panel sectors armed → away
        if len(panel_armed) == panel_total:
            return AlarmControlPanelState.ARMED_AWAY

        # Partial overlap: pick the mode with the most matching sectors
        matches = [
            (len(panel_armed & sectors), STATE_PRIORITY.get(state, 0), state)
            for state, sectors in options_map.items()
            if panel_armed & sectors
        ]
        if matches:
            matches.sort(reverse=True)
            return matches[0][2]

        # Armed but no configured profile matches
        return AlarmControlPanelState.ARMED_CUSTOM_BYPASS

    @property
    def available(self) -> bool:
        """Entity availability based on coordinator status."""

        return super().available and self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose additional panel metadata."""
        snapshot = self.coordinator.data
        if snapshot is None or snapshot.status is None:
            return {}

        status = snapshot.status
        armed_bits = status.armed
        triggered_bits = status.triggered
        armed_sectors_all = {i + 1 for i, bit in enumerate(armed_bits) if bit}
        disarmed_sectors_all = {i + 1 for i, bit in enumerate(armed_bits) if not bit}
        triggered_sectors_all = {i + 1 for i, bit in enumerate(triggered_bits) if bit}

        # limita la vista al pannello
        if self._managed_sectors:
            scope = sorted(self._managed_sectors)
            armed_sectors = sorted(armed_sectors_all & self._managed_sectors)
            disarmed_sectors = sorted(disarmed_sectors_all & self._managed_sectors)
            triggered_sectors = sorted(
                triggered_sectors_all & self._managed_sectors
            )
            # ricostruisco i bit solo per i settori gestiti
            raw_bits = [bool(armed_bits[i - 1]) for i in scope]
            raw_trigger_bits = [bool(triggered_bits[i - 1]) for i in scope]
        else:
            scope = list(range(1, len(armed_bits) + 1))
            armed_sectors = sorted(armed_sectors_all)
            disarmed_sectors = sorted(disarmed_sectors_all)
            triggered_sectors = sorted(triggered_sectors_all)
            raw_bits = list(armed_bits)
            raw_trigger_bits = list(triggered_bits)

        result = {
            "armed_sectors": armed_sectors,
            "disarmed_sectors": disarmed_sectors,
            "raw_sector_bits": raw_bits,
            "triggered_sectors": triggered_sectors,
            "raw_trigger_bits": raw_trigger_bits,
            "panel_managed_sectors": scope,
            "panel_slug": self._panel.slug,
        }

        armed_set = set(armed_sectors)
        for mode, sectors in self._mode_sectors.items():
            if sectors:
                state_key = MODE_TO_STATE[mode].value
                result[f"configured_{mode}_sectors"] = sorted(sectors)
                result[f"is_{state_key}"] = armed_set == sectors

        return result
