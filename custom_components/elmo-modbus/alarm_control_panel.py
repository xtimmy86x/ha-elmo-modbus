"""Alarm control panel entity for the Elmo Modbus integration."""

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

from .const import (
    DOMAIN,
    OPTION_ARMED_AWAY_SECTORS,
    OPTION_ARMED_HOME_SECTORS,
    OPTION_ARMED_NIGHT_SECTORS,
    OPTION_DISARM_SECTORS,
    REGISTER_COMMAND_COUNT,
    REGISTER_COMMAND_START,
    REGISTER_STATUS_COUNT,
)
from .coordinator import ElmoModbusCoordinator

MODE_LABELS = {
    OPTION_ARMED_AWAY_SECTORS: "Arm Away",
    OPTION_ARMED_HOME_SECTORS: "Arm Home",
    OPTION_ARMED_NIGHT_SECTORS: "Arm Night",
}

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the alarm control panel entity from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusCoordinator = data["coordinator"]
    client: ModbusTcpClient = data["client"]

    async_add_entities([ElmoModbusAlarmControlPanel(entry, coordinator, client)])


class ElmoModbusAlarmControlPanel(CoordinatorEntity[ElmoModbusCoordinator], AlarmControlPanelEntity):
    """Representation of the Modbus-backed alarm panel."""

    _attr_has_entity_name = True
    _attr_name = "Alarm Panel"
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )
    _attr_code_arm_required = False

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        client: ModbusTcpClient,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._config_entry = entry
        self._host = entry.data["host"]
        self._port = entry.data["port"]
        self._client = client

    @property
    def _all_sectors(self) -> set[int]:
        """Return a set with all known sector numbers."""

        return {index + 1 for index in range(REGISTER_STATUS_COUNT)}
    
    def _target_sectors(self, option_key: str, *, default_to_all: bool = False) -> set[int]:
        """Return the sectors that should be armed for a specific mode."""

        sectors = self._sectors_for_option(option_key)
        if sectors:
            return sectors
        if default_to_all:
            return self._all_sectors
        mode = MODE_LABELS.get(option_key, option_key)
        raise HomeAssistantError(f"No sectors configured for {mode} arming mode")

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
            raise HomeAssistantError(f"Failed to send command to {self._host}:{self._port}") from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send a Modbus command to disarm all sectors."""

        await self._async_send_command(
            self._target_sectors(OPTION_DISARM_SECTORS, default_to_all=True),
            value=False,
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured away sectors."""

        await self._async_send_command(
            self._target_sectors(OPTION_ARMED_AWAY_SECTORS, default_to_all=True),
            value=True,
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured home sectors."""

        await self._async_send_command(
            self._target_sectors(OPTION_ARMED_HOME_SECTORS),
            value=True,
        )

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send a Modbus command to arm the configured night sectors."""

        await self._async_send_command(
            self._target_sectors(OPTION_ARMED_NIGHT_SECTORS),
            value=True,
        )

    def _sectors_for_option(self, option_key: str) -> set[int]:
        """Return the configured sector set for a specific arming mode."""

        sectors = self._config_entry.options.get(option_key, [])
        return {sector for sector in sectors if 1 <= sector <= REGISTER_STATUS_COUNT}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the alarm panel."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current state of the alarm panel."""
        bits = self.coordinator.data
        if bits is None:
            return None

        armed_count = sum(bits)
        if armed_count == 0:
            return AlarmControlPanelState.DISARMED
        
        armed_sectors = {index + 1 for index, bit in enumerate(bits) if bit}

        options_map = {
            AlarmControlPanelState.ARMED_AWAY: self._sectors_for_option(
                OPTION_ARMED_AWAY_SECTORS
            ),
            AlarmControlPanelState.ARMED_HOME: self._sectors_for_option(
                OPTION_ARMED_HOME_SECTORS
            ),
            AlarmControlPanelState.ARMED_NIGHT: self._sectors_for_option(
                OPTION_ARMED_NIGHT_SECTORS
            ),
        }

        for state, sectors in options_map.items():
            if sectors and armed_sectors == sectors:
                return state

        if armed_count == REGISTER_STATUS_COUNT:
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.DISARMED

    @property
    def available(self) -> bool:
        """Entity availability based on coordinator status."""
        return super().available and self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw register value as an attribute."""
        bits = self.coordinator.data
        if bits is None:
            return {}

        armed_sectors = [index + 1 for index, bit in enumerate(bits) if bit]
        disarmed_sectors = [index + 1 for index, bit in enumerate(bits) if not bit]

        result = {
            "armed_sectors": armed_sectors,
            "disarmed_sectors": disarmed_sectors,
            "raw_sector_bits": bits,
        }

        armed_sectors_set = set(armed_sectors)
        for state, option_key in (
            ("armed_away", OPTION_ARMED_AWAY_SECTORS),
            ("armed_home", OPTION_ARMED_HOME_SECTORS),
            ("armed_night", OPTION_ARMED_NIGHT_SECTORS),
        ):
            configured = self._sectors_for_option(option_key)
            if configured:
                result[f"configured_{state}_sectors"] = sorted(configured)
                result[f"is_{state}"] = armed_sectors_set == configured

        return result