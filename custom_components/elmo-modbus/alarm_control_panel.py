"""Alarm control panel entities for the Elmo Modbus integration."""

from __future__ import annotations

from typing import Any, Iterable

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REGISTER_COMMAND_COUNT, REGISTER_COMMAND_START, REGISTER_STATUS_COUNT
from .coordinator import ElmoModbusCoordinator
from .panels import MODES, PanelDefinition, load_panel_definitions

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
    client: ModbusTcpClient = data["client"]

    panels = load_panel_definitions(entry.options)
    entities = [
        ElmoModbusAlarmControlPanel(entry, coordinator, client, panel)
        for panel in panels
    ]

    if entities:
        async_add_entities(entities)

class ElmoModbusAlarmControlPanel(CoordinatorEntity[ElmoModbusCoordinator], AlarmControlPanelEntity):
    """Representation of the Modbus-backed alarm panel."""

    _attr_has_entity_name = True
    _attr_code_arm_required = False

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        client: ModbusTcpClient,
        panel: PanelDefinition,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._panel = panel
        self._config_entry = entry
        self._host = entry.data["host"]
        self._port = entry.data["port"]
        self._client = client

        self._attr_unique_id = f"{entry.entry_id}:{panel.slug}"
        self._attr_name = panel.name
        self.entity_id = f"alarm_control_panel.{panel.slug}"

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

        return {index + 1 for index in range(REGISTER_STATUS_COUNT)}
    
    def _target_sectors(self, mode: str) -> set[int]:
        """Return the sectors that should be armed for a specific mode."""

        sectors = self._mode_sectors.get(mode)
        if sectors:
            return sectors
        raise HomeAssistantError(
            f"No sectors configured for {MODE_LABELS.get(mode, mode)} on panel {self._panel.name}"
        )

    def _build_command_payload(
        self, target_sectors: Iterable[int], *, value: bool
    ) -> list[bool]:
        """Convert a sector iterable into a bit payload for the command coils."""

        if (
            (current := self.coordinator.data)
            and len(current) >= REGISTER_COMMAND_COUNT
        ):
            payload = list(current[:REGISTER_COMMAND_COUNT])
        else:
            payload = [False] * REGISTER_COMMAND_COUNT
        for sector in target_sectors:
            if 1 <= sector <= REGISTER_COMMAND_COUNT:
                payload[sector - 1] = value
        return payload

    async def _async_send_command(
        self, target_sectors: Iterable[int], *, value: bool
    ) -> None:
        """Send the Modbus command to set the desired arming state."""

        payload = self._build_command_payload(target_sectors, value=value)

        def _write() -> None:
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

            response = self._client.write_coils(REGISTER_COMMAND_START, payload)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when writing coils")

        try:
            await self.hass.async_add_executor_job(_write)
        except ConnectionException as err:
            raise HomeAssistantError(
                f"Failed to send command to {self._host}:{self._port}"
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send a Modbus command to disarm the configured sectors."""

        target = self._managed_sectors or self._all_sectors
        await self._async_send_command(target, value=False)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured away sectors."""

        await self._async_send_command(self._target_sectors("away"), value=True)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured home sectors."""

        await self._async_send_command(self._target_sectors("home"), value=True)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured night sectors."""

        await self._async_send_command(self._target_sectors("night"), value=True)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the alarm panel."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current state of the alarm panel."""

        bits = self.coordinator.data
        if bits is None:
            return None

        armed_sectors = {i + 1 for i, b in enumerate(bits) if bool(b)}
        armed_count = len(armed_sectors)
        total = len(bits)

        if armed_count == 0:
            return AlarmControlPanelState.DISARMED

        # set configurati per ciascuna modalità
        options_map: dict[AlarmControlPanelState, set[int]] = {
            MODE_TO_STATE[mode]: sectors for mode, sectors in self._mode_sectors.items()
        }

        for state, sectors in options_map.items():
            if armed_sectors == sectors:
                return state

        if armed_count == total:
            return AlarmControlPanelState.ARMED_AWAY

        # 3) match per intersezione: scegli il profilo con overlap massimo, poi per priorità
        matches = []
        for state, sectors in options_map.items():
            overlap = len(armed_sectors & sectors)
            if overlap > 0:
                matches.append((overlap, STATE_PRIORITY.get(state, 0), state))

        if matches:
            matches.sort(reverse=True)
            return matches[0][2]
        try:
            return AlarmControlPanelState.ARMED_CUSTOM_BYPASS
        except AttributeError:
            return AlarmControlPanelState.ARMED_AWAY

    @property
    def available(self) -> bool:
        """Entity availability based on coordinator status."""

        return super().available and self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose additional panel metadata."""
        bits = self.coordinator.data
        if bits is None:
            return {}

        armed_sectors = [index + 1 for index, bit in enumerate(bits) if bit]
        disarmed_sectors = [index + 1 for index, bit in enumerate(bits) if not bit]

        result = {
            "armed_sectors": armed_sectors,
            "disarmed_sectors": disarmed_sectors,
            "raw_sector_bits": bits,
            "panel_managed_sectors": sorted(self._managed_sectors),
            "panel_slug": self._panel.slug,
        }

        armed_sectors_set = set(armed_sectors)
        for mode, sectors in self._mode_sectors.items():
            if sectors:
                state_key = MODE_TO_STATE[mode].value
                result[f"configured_{mode}_sectors"] = sorted(sectors)
                result[f"is_{state_key}"] = armed_sectors_set == sectors

        return result