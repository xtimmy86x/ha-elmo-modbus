from __future__ import annotations

"""Switch platform for controlling Elmo Modbus outputs."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from pymodbus.exceptions import ConnectionException

from .const import (
    CONF_OUTPUT_SWITCHES,
    CONF_SECTOR_SWITCHES,
    DEFAULT_SECTORS,
    DOMAIN,
    INOUT_MAX_COUNT,
    OPTION_OUTPUT_NAMES,
    OPTION_SECTOR_SWITCH_NAMES,
    OUTPUT_SWITCH_START,
    REGISTER_COMMAND_START,
)
from .coordinator import ElmoModbusCoordinator, ElmoModbusInventory
from .input_selectors import normalize_input_sensor_config

import logging
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ElmoSwitchDescription(SwitchEntityDescription):
    """Description of an Elmo Modbus output switch."""

    address: int
    object_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class ElmoSectorSwitchDescription(SwitchEntityDescription):
    """Description of an Elmo Modbus sector switch."""

    sector: int
    object_id: str | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elmo Modbus switches."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusCoordinator = data["coordinator"]
    inventory: ElmoModbusInventory = data["inventory"]

    raw_switches = entry.options.get(CONF_OUTPUT_SWITCHES)
    switch_ids = normalize_input_sensor_config(raw_switches, max_input=INOUT_MAX_COUNT)

    if not switch_ids and CONF_OUTPUT_SWITCHES in entry.data:
        switch_ids = normalize_input_sensor_config(
            entry.data.get(CONF_OUTPUT_SWITCHES),
            max_input=INOUT_MAX_COUNT,
        )

    raw_names = entry.options.get(OPTION_OUTPUT_NAMES, {})
    output_names: dict[int, str] = {}
    if isinstance(raw_names, dict):
        for key, value in raw_names.items():
            try:
                switch = int(key)
            except (TypeError, ValueError):
                continue
            if switch not in switch_ids:
                continue
            name = str(value).strip()
            if name:
                output_names[switch] = name

    descriptions: list[ElmoSwitchDescription] = []
    used_object_ids: set[str] = set()
    for index in sorted(switch_ids):
        address = OUTPUT_SWITCH_START + index - 1
        custom_name = output_names.get(index)
        description_kwargs: dict[str, Any] = {
            "key": f"output_switch_{index}",
            "address": address,
        }

        if custom_name:
            description_kwargs["name"] = custom_name
        else:
            description_kwargs["translation_key"] = "output_switch"
            description_kwargs["translation_placeholders"] = {"index": str(index)}

        if custom_name:
            object_id = slugify(custom_name) or f"output_switch_{index}"
        else:
            object_id = f"output_switch_{index}"

        if object_id in used_object_ids:
            object_id = f"{object_id}_{index}"
        used_object_ids.add(object_id)

        description_kwargs["object_id"] = object_id

        descriptions.append(ElmoSwitchDescription(**description_kwargs))

    if not descriptions:
        return

    addresses = tuple(description.address for description in descriptions)

    entity_registry = er.async_get(hass)
    for description in descriptions:
        if not description.object_id:
            continue

        unique_id = f"{entry.entry_id}:switch:{description.key}"
        entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
        if entity_id is None:
            continue

        device_slug = slugify(entry.title)
        desired_entity_id = f"switch.{device_slug}_{description.object_id}"
        if entity_id == desired_entity_id:
            continue

        existing_entry = entity_registry.entities.get(desired_entity_id)
        if existing_entry is not None and existing_entry.unique_id != unique_id:
            continue

        entity_registry.async_update_entity(entity_id, new_entity_id=desired_entity_id)

    if inventory.add_coils(addresses):
        await coordinator.async_request_refresh()

    entities = [
        ElmoModbusSwitch(entry, coordinator, inventory, description)
        for description in descriptions
    ]

    if entities:
        async_add_entities(entities)

    # --- Sector switches ---
    raw_sector_switches = entry.options.get(CONF_SECTOR_SWITCHES, [])
    sector_ids: list[int] = []
    sector_limit = int(entry.data.get("sectors", DEFAULT_SECTORS))
    if isinstance(raw_sector_switches, list):
        for item in raw_sector_switches:
            try:
                sid = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= sid <= sector_limit:
                sector_ids.append(sid)
        sector_ids = sorted(set(sector_ids))

    if not sector_ids:
        return

    raw_sector_names = entry.options.get(OPTION_SECTOR_SWITCH_NAMES, {})
    sector_names: dict[int, str] = {}
    if isinstance(raw_sector_names, dict):
        for key, value in raw_sector_names.items():
            try:
                sector = int(key)
            except (TypeError, ValueError):
                continue
            if sector not in sector_ids:
                continue
            name = str(value).strip()
            if name:
                sector_names[sector] = name

    sector_descriptions: list[ElmoSectorSwitchDescription] = []
    used_sector_ids: set[str] = set()
    for sector in sector_ids:
        custom_name = sector_names.get(sector)
        desc_kwargs: dict[str, Any] = {
            "key": f"sector_switch_{sector}",
            "sector": sector,
        }

        if custom_name:
            desc_kwargs["name"] = custom_name
        else:
            desc_kwargs["translation_key"] = "sector_switch"
            desc_kwargs["translation_placeholders"] = {"index": str(sector)}

        if custom_name:
            obj_id = slugify(custom_name) or f"sector_switch_{sector}"
        else:
            obj_id = f"sector_switch_{sector}"

        if obj_id in used_sector_ids:
            obj_id = f"{obj_id}_{sector}"
        used_sector_ids.add(obj_id)

        desc_kwargs["object_id"] = obj_id
        sector_descriptions.append(ElmoSectorSwitchDescription(**desc_kwargs))

    if not sector_descriptions:
        return

    entity_registry = er.async_get(hass)
    for desc in sector_descriptions:
        if not desc.object_id:
            continue

        unique_id = f"{entry.entry_id}:switch:{desc.key}"
        entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
        if entity_id is None:
            continue

        device_slug = slugify(entry.title)
        desired_entity_id = f"switch.{device_slug}_{desc.object_id}"
        if entity_id == desired_entity_id:
            continue

        existing_entry = entity_registry.entities.get(desired_entity_id)
        if existing_entry is not None and existing_entry.unique_id != unique_id:
            continue

        entity_registry.async_update_entity(entity_id, new_entity_id=desired_entity_id)

    sector_entities = [
        ElmoSectorSwitch(entry, coordinator, inventory, desc)
        for desc in sector_descriptions
    ]

    if sector_entities:
        async_add_entities(sector_entities)


class ElmoModbusSwitch(CoordinatorEntity[ElmoModbusCoordinator], SwitchEntity):
    """Representation of an Elmo Modbus output switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        inventory: ElmoModbusInventory,
        description: ElmoSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._inventory = inventory
        self._attr_unique_id = f"{entry.entry_id}:switch:{description.key}"
        if description.object_id:
            self._attr_suggested_object_id = description.object_id

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""

        snapshot = self.coordinator.data
        if not snapshot:
            return None
        value = snapshot.coils.get(self.entity_description.address)
        if value is None:
            return None
        return bool(value)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information shared across entities."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name=self._config_entry.title,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate the output."""

        await self._async_write_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate the output."""

        await self._async_write_state(False)

    async def _async_write_state(self, value: bool) -> None:
        """Write the desired state to the Modbus coil."""

        address = self.entity_description.address

        def _write() -> None:
            self._inventory.write_coil(address, value)

        try:
            await self.hass.async_add_executor_job(_write)
        except ConnectionException as err:
            raise HomeAssistantError(
                f"Failed to update output {address}: {err}"
            ) from err
        except Exception as err:  # pragma: no cover - unexpected failure guard
            raise HomeAssistantError(
                f"Unexpected error while updating output {address}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()


class ElmoSectorSwitch(CoordinatorEntity[ElmoModbusCoordinator], SwitchEntity):
    """Switch to arm/disarm an individual alarm sector."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusCoordinator,
        inventory: ElmoModbusInventory,
        description: ElmoSectorSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._inventory = inventory
        self._sector = description.sector
        self._attr_unique_id = f"{entry.entry_id}:switch:{description.key}"
        if description.object_id:
            self._attr_suggested_object_id = description.object_id

    @property
    def is_on(self) -> bool | None:
        """Return True when the sector is armed."""

        snapshot = self.coordinator.data
        if not snapshot or not snapshot.status:
            return None
        armed = snapshot.status.armed
        index = self._sector - 1
        if index >= len(armed):
            return None
        return bool(armed[index])

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information shared across entities."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name=self._config_entry.title,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm the sector."""

        await self._async_write_sector(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm the sector."""

        await self._async_write_sector(False)

    async def _async_write_sector(self, value: bool) -> None:
        """Write the desired arming state for this sector."""

        snapshot = self.coordinator.data
        status = snapshot.status if snapshot else None

        if status:
            payload = list(status.armed)
        else:
            span = max(1, min(self.coordinator.sector_count, DEFAULT_SECTORS))
            payload = [False] * span

        index = self._sector - 1
        if index >= len(payload):
            raise HomeAssistantError(
                f"Sector {self._sector} is out of range"
            )

        payload[index] = value

        def _write() -> None:
            self._inventory.write_coils(REGISTER_COMMAND_START, payload)

        try:
            await self.hass.async_add_executor_job(_write)
        except ConnectionException as err:
            raise HomeAssistantError(
                f"Failed to update sector {self._sector}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()
