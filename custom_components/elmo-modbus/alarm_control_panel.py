"""Alarm control panel entity for the Elmo Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REGISTER_STATUS_COUNT
from .coordinator import ElmoModbusCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the alarm control panel entity from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusCoordinator = data["coordinator"]

    async_add_entities([ElmoModbusAlarmControlPanel(entry, coordinator)])


class ElmoModbusAlarmControlPanel(CoordinatorEntity[ElmoModbusCoordinator], AlarmControlPanelEntity):
    """Representation of the Modbus-backed alarm panel."""

    _attr_has_entity_name = True
    _attr_name = "Alarm Panel"
    _attr_supported_features = AlarmControlPanelEntityFeature(0)
    _attr_code_arm_required = False
    _attr_alarm_state: AlarmControlPanelState | None = None

    def __init__(self, entry: ConfigEntry, coordinator: ElmoModbusCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._host = entry.data["host"]
        self._port = entry.data["port"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the alarm panel."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()
        self._attr_alarm_state = self._derive_alarm_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update internal state from coordinator data."""
        self._attr_alarm_state = self._derive_alarm_state()
        super()._handle_coordinator_update()

    def _derive_alarm_state(self) -> AlarmControlPanelState | None:
        """Translate raw Modbus bits into an alarm state."""
        bits = self.coordinator.data
        if bits is None:
            return None

        armed_count = sum(bits)
        if armed_count == 0:
            return AlarmControlPanelState.DISARMED
        if armed_count == REGISTER_STATUS_COUNT:
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.ARMED_HOME

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current state of the alarm panel."""
        return self._attr_alarm_state

    @property
    def state(self) -> str | None:
        """Alias for backwards compatibility with the legacy state property."""
        current_state = self._attr_alarm_state
        return None if current_state is None else current_state.value

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

        return {
            "armed_sectors": armed_sectors,
            "disarmed_sectors": disarmed_sectors,
            "raw_sector_bits": bits,
        }