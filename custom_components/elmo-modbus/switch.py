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
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from .const import (
    CONF_OUTPUT_SWITCHES,
    CONF_SCAN_INTERVAL,
    DEFAULT_OUTPUT_SWITCHES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPTION_OUTPUT_NAMES,
    OUTPUT_SWITCH_COUNT,
    OUTPUT_SWITCH_START,
)
from .coordinator import ElmoModbusSwitchCoordinator
from .input_selectors import normalize_input_sensor_config


@dataclass(frozen=True, kw_only=True)
class ElmoSwitchDescription(SwitchEntityDescription):
    """Description of an Elmo Modbus output switch."""

    address: int
    object_id: str | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elmo Modbus switches."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ElmoModbusSwitchCoordinator | None = data.get("switch_coordinator")
    client: ModbusTcpClient = data["client"]

    raw_switches = entry.options.get(CONF_OUTPUT_SWITCHES)
    switch_ids = normalize_input_sensor_config(
        raw_switches, max_input=OUTPUT_SWITCH_COUNT
    )

    if not switch_ids:
        switch_ids = normalize_input_sensor_config(
            entry.data.get(CONF_OUTPUT_SWITCHES, DEFAULT_OUTPUT_SWITCHES),
            max_input=OUTPUT_SWITCH_COUNT,
        )

    if not switch_ids:
        switch_ids = normalize_input_sensor_config(
            DEFAULT_OUTPUT_SWITCHES, max_input=OUTPUT_SWITCH_COUNT
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

        desired_entity_id = f"switch.{description.object_id}"
        if entity_id == desired_entity_id:
            continue

        existing_entry = entity_registry.entities.get(desired_entity_id)
        if existing_entry is not None and existing_entry.unique_id != unique_id:
            continue

        entity_registry.async_update_entity(entity_id, new_entity_id=desired_entity_id)

    if coordinator is None or set(coordinator.addresses) != set(addresses):
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        coordinator = ElmoModbusSwitchCoordinator(
            hass,
            client,
            addresses=addresses,
            scan_interval=scan_interval,
        )
        await coordinator.async_config_entry_first_refresh()
        data["switch_coordinator"] = coordinator

    entities = [
        ElmoModbusSwitch(entry, coordinator, client, description)
        for description in descriptions
    ]

    if entities:
        async_add_entities(entities)


class ElmoModbusSwitch(CoordinatorEntity[ElmoModbusSwitchCoordinator], SwitchEntity):
    """Representation of an Elmo Modbus output switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ElmoModbusSwitchCoordinator,
        client: ModbusTcpClient,
        description: ElmoSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}:switch:{description.key}"
        if description.object_id:
            self._attr_suggested_object_id = description.object_id

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""

        data = self.coordinator.data
        if not data:
            return None
        value = data.get(self.entity_description.address)
        if value is None:
            return None
        return bool(value)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information shared across entities."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Elmo",
            name="Elmo Modbus Control Panel",
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
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

            response = self._client.write_coil(address, value)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when writing coil")

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
