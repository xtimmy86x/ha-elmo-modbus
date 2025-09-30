"""Binary sensors for Elmo Modbus diagnostic states."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_INPUT_SENSORS,
    CONF_SCAN_INTERVAL,
    DEFAULT_INPUT_SENSORS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INPUT_SENSOR_COUNT,
    INPUT_SENSOR_START,
)
from .coordinator import ElmoModbusBinarySensorCoordinator
from .input_selectors import normalize_input_sensor_config


@dataclass(frozen=True, kw_only=True)
class ElmoBinarySensorDescription(BinarySensorEntityDescription):
    """Description of an Elmo Modbus binary sensor."""

    address: int


BASE_SENSOR_DESCRIPTIONS: tuple[ElmoBinarySensorDescription, ...] = (
    ElmoBinarySensorDescription(
        key="central_power_fault",
        translation_key="central_power_fault",
        address=0x0100,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="central_battery_fault",
        translation_key="central_battery_fault",
        address=0x0101,
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="central_tamper_fault",
        translation_key="central_tamper_fault",
        address=0x0102,
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="pstn_fault",
        translation_key="pstn_fault",
        address=0x0103,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="cellular_fault",
        translation_key="cellular_fault",
        address=0x0104,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sensor_power_fault_1",
        translation_key="sensor_power_fault_1",
        address=0x0105,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sensor_power_fault_2",
        translation_key="sensor_power_fault_2",
        address=0x0106,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="siren_power_fault",
        translation_key="siren_power_fault",
        address=0x0107,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="central_general_alarm",
        translation_key="central_general_alarm",
        address=0x0200,
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="central_general_tamper",
        translation_key="central_general_tamper",
        address=0x0201,
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sectors_not_armable",
        translation_key="sectors_not_armable",
        address=0x0401,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sectors_inserted",
        translation_key="sectors_inserted",
        address=0x0402,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sectors_inserted_max_security",
        translation_key="sectors_inserted_max_security",
        address=0x0403,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sectors_inputs_alarm",
        translation_key="sectors_inputs_alarm",
        address=0x0404,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="sectors_inputs_memory_alarm",
        translation_key="sectors_inputs_memory_alarm",
        address=0x0405,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ElmoBinarySensorDescription(
        key="excluded_zones",
        translation_key="excluded_zones",
        address=0x0406,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elmo Modbus binary sensors."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusBinarySensorCoordinator | None = data.get(
        "binary_coordinator"
    )

    raw_input_sensors = entry.data.get(CONF_INPUT_SENSORS, DEFAULT_INPUT_SENSORS)
    input_sensor_ids = normalize_input_sensor_config(
        raw_input_sensors, max_input=INPUT_SENSOR_COUNT
    )

    if not input_sensor_ids:
        fallback_limit = min(DEFAULT_INPUT_SENSORS, INPUT_SENSOR_COUNT)
        input_sensor_ids = list(range(1, fallback_limit + 1))

    input_descriptions = [
        ElmoBinarySensorDescription(
            key=f"alarm_input_{index}",
            translation_key="input_alarm",
            translation_placeholders={"index": str(index)},
            address=INPUT_SENSOR_START + index - 1,
            device_class=BinarySensorDeviceClass.SAFETY,
        )
        for index in input_sensor_ids
    ]

    descriptions = [*BASE_SENSOR_DESCRIPTIONS, *input_descriptions]
    addresses = tuple(description.address for description in descriptions)

    if coordinator is None or set(coordinator.addresses) != set(addresses):
        client = data["client"]
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        coordinator = ElmoModbusBinarySensorCoordinator(
            hass,
            client,
            addresses=addresses,
            scan_interval=scan_interval,
        )
        await coordinator.async_config_entry_first_refresh()
        data["binary_coordinator"] = coordinator

    entities = [
        ElmoModbusBinarySensor(entry, coordinator, description)
        for description in descriptions
    ]

    if entities:
        async_add_entities(entities)


class ElmoModbusBinarySensor(
    CoordinatorEntity[ElmoModbusBinarySensorCoordinator], BinarySensorEntity
):
    """Representation of an Elmo Modbus diagnostic binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusBinarySensorCoordinator,
        description: ElmoBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._attr_unique_id = f"{entry.entry_id}:binary:{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""

        data = self.coordinator.data
        if not data:
            return None
        value = data.get(self.entity_description.address)
        if value is None:
            return None
        return bool(value)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information for these sensors."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
        )
