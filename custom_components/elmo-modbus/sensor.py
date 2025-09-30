"""Sensors for Elmo Modbus holding registers."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ElmoModbusSensorCoordinator


@dataclass(frozen=True, kw_only=True)
class ElmoSensorDescription(SensorEntityDescription):
    """Description of an Elmo Modbus sensor."""

    address: int
    invalid_values: tuple[int, ...] = ()


SENSOR_DESCRIPTIONS: tuple[ElmoSensorDescription, ...] = (
    ElmoSensorDescription(
        key="central_temperature",
        translation_key="central_temperature",
        address=0x0180,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        invalid_values=(0x8000,),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elmo Modbus sensors."""

    if not SENSOR_DESCRIPTIONS:
        return

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusSensorCoordinator | None = data.get("sensor_coordinator")

    if coordinator is None:
        client = data["client"]
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        coordinator = ElmoModbusSensorCoordinator(
            hass,
            client,
            addresses=[description.address for description in SENSOR_DESCRIPTIONS],
            scan_interval=scan_interval,
        )
        await coordinator.async_config_entry_first_refresh()
        data["sensor_coordinator"] = coordinator

    entities = [
        ElmoModbusSensor(entry, coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    if entities:
        async_add_entities(entities)


class ElmoModbusSensor(CoordinatorEntity[ElmoModbusSensorCoordinator], SensorEntity):
    """Representation of an Elmo Modbus holding register sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusSensorCoordinator,
        description: ElmoSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._attr_unique_id = f"{entry.entry_id}:sensor:{description.key}"

    @staticmethod
    def _as_signed_16bit(value: int) -> int:
        """Convert an unsigned 16-bit integer to a signed value."""

        return value - 0x10000 if value & 0x8000 else value

    @property
    def native_value(self) -> float | None:
        """Return the processed value reported by the sensor."""

        data = self.coordinator.data
        if not data:
            return None

        raw_value = data.get(self.entity_description.address)
        if raw_value is None:
            return None
        if raw_value in self.entity_description.invalid_values:
            return None

        signed_value = self._as_signed_16bit(raw_value)
        return signed_value / 10

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information for this sensor."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
        )