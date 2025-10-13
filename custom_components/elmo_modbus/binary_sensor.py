"""Binary sensors for Elmo Modbus diagnostic states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    CONF_INPUT_SENSORS,
    DOMAIN,
    INOUT_MAX_COUNT,
    INPUT_SENSOR_EXCLUDED_START,
    INPUT_SENSOR_START,
    OPTION_INPUT_NAMES,
)
from .coordinator import ElmoModbusCoordinator, ElmoModbusInventory
from .input_selectors import normalize_input_sensor_config

import logging
_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class ElmoBinarySensorDescription(BinarySensorEntityDescription):
    """Description of an Elmo Modbus binary sensor."""

    address: int
    object_id: str | None = None
    excluded_address: int | None = None


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
    coordinator: ElmoModbusCoordinator = data["coordinator"]
    inventory: ElmoModbusInventory = data["inventory"]

    raw_input_sensors = entry.options.get(CONF_INPUT_SENSORS)
    input_sensor_ids = normalize_input_sensor_config(
        raw_input_sensors, max_input=INOUT_MAX_COUNT
    )

    if not input_sensor_ids and CONF_INPUT_SENSORS in entry.data:
        input_sensor_ids = normalize_input_sensor_config(
            entry.data.get(CONF_INPUT_SENSORS),
            max_input=INOUT_MAX_COUNT,
        )

    raw_names = entry.options.get(OPTION_INPUT_NAMES, {})
    input_names: dict[int, str] = {}
    if isinstance(raw_names, dict):
        for key, value in raw_names.items():
            try:
                sensor = int(key)
            except (TypeError, ValueError):
                continue
            if sensor not in input_sensor_ids:
                continue
            name = str(value).strip()
            if name:
                input_names[sensor] = name

    input_descriptions: list[ElmoBinarySensorDescription] = []
    used_object_ids: set[str] = set()
    for index in sorted(input_sensor_ids):
        custom_name = input_names.get(index)
        description_kwargs: dict[str, Any] = {
            "key": f"alarm_input_{index}",
            "address": INPUT_SENSOR_START + index - 1,
            "device_class": BinarySensorDeviceClass.SAFETY,
            "excluded_address": INPUT_SENSOR_EXCLUDED_START + index - 1,
        }

        if custom_name:
            description_kwargs["name"] = custom_name
        else:
            description_kwargs["translation_key"] = "input_alarm"
            description_kwargs["translation_placeholders"] = {"index": str(index)}

        if custom_name:
            object_id = slugify(custom_name)
            if not object_id:
                object_id = f"alarm_input_{index}"
        else:
            object_id = f"alarm_input_{index}"

        if object_id in used_object_ids:
            object_id = f"{object_id}_{index}"
        used_object_ids.add(object_id)

        description_kwargs["object_id"] = object_id

        input_descriptions.append(ElmoBinarySensorDescription(**description_kwargs))

    descriptions = [*BASE_SENSOR_DESCRIPTIONS, *input_descriptions]
    address_set: set[int] = set()
    for description in descriptions:
        address_set.add(description.address)
        if description.excluded_address is not None:
            address_set.add(description.excluded_address)

    addresses = tuple(sorted(address_set))

    entity_registry = er.async_get(hass)
    for description in input_descriptions:
        if not description.object_id:
            continue

        unique_id = f"{entry.entry_id}:binary:{description.key}"
        entity_id = entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, unique_id
        )
        if entity_id is None:
            continue

        desired_entity_id = f"binary_sensor.{description.object_id}"
        if entity_id == desired_entity_id:
            continue

        existing_entry = entity_registry.entities.get(desired_entity_id)
        if existing_entry is not None and existing_entry.unique_id != unique_id:
            continue

        entity_registry.async_update_entity(entity_id, new_entity_id=desired_entity_id)

    if inventory.add_discrete_inputs(addresses):
        await coordinator.async_request_refresh()

    entities = [
        ElmoModbusBinarySensor(entry, coordinator, description)
        for description in descriptions
    ]

    if entities:
        async_add_entities(entities)


class ElmoModbusBinarySensor(CoordinatorEntity[ElmoModbusCoordinator], BinarySensorEntity):
    """Representation of an Elmo Modbus diagnostic binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        description: ElmoBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._attr_unique_id = f"{entry.entry_id}:binary:{description.key}"
        if description.object_id:
            self._attr_suggested_object_id = description.object_id

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""

        snapshot = self.coordinator.data
        if not snapshot:
            return None
        value = snapshot.discrete_inputs.get(self.entity_description.address)
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

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return additional state attributes for the binary sensor."""
        snapshot = self.coordinator.data
        if not snapshot:
            return None

        attrs: dict[str, str] = {}

        excluded_addr = self.entity_description.excluded_address
        if excluded_addr is None:
            return attrs  # nessun attributo "excluded" per questo sensore

        excluded_value = snapshot.discrete_inputs.get(excluded_addr)
        if excluded_value is None:
            # il coordinatore non ha (ancora) il valore: non esporre l'attributo
            return attrs

        attrs["excluded"] = "on" if bool(excluded_value) else "off"
        return attrs
