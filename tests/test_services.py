from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.elmo_modbus import services
from custom_components.elmo_modbus.const import (
    DOMAIN,
    INPUT_SENSOR_EXCLUDED_START,
)


class DummyInventory:
    def __init__(self) -> None:
        self.writes: list[tuple[int, bool]] = []

    def write_coil(self, address: int, value: bool) -> None:
        self.writes.append((address, value))


class DummyCoordinator:
    def __init__(self) -> None:
        self.refreshed = False

    async def async_request_refresh(self) -> None:
        self.refreshed = True


def test_group_input_entities_by_entry() -> None:
    hass = HomeAssistant()
    hass.data.setdefault(DOMAIN, {})["entry1"] = {
        "inventory": object(),
        "coordinator": object(),
    }

    registry = er.async_get(hass)
    registry.entities["binary_sensor.elmo_modbus_input_5"] = er.RegistryEntry(
        entity_id="binary_sensor.elmo_modbus_input_5",
        unique_id="entry1:binary:alarm_input_5",
        platform=DOMAIN,
        config_entry_id="entry1",
    )

    mapping = services._group_input_entities_by_entry(
        hass, ["binary_sensor.elmo_modbus_input_5"]
    )

    assert mapping == {"entry1": {5}}


def test_async_handle_set_input_exclusion_uses_target_entities() -> None:
    hass = HomeAssistant()
    inventory = DummyInventory()
    coordinator = DummyCoordinator()
    hass.data.setdefault(DOMAIN, {})["entry1"] = {
        "inventory": inventory,
        "coordinator": coordinator,
    }

    registry = er.async_get(hass)
    registry.entities["binary_sensor.elmo_modbus_input_3"] = er.RegistryEntry(
        entity_id="binary_sensor.elmo_modbus_input_3",
        unique_id="entry1:binary:alarm_input_3",
        platform=DOMAIN,
        config_entry_id="entry1",
    )
    registry.entities["binary_sensor.elmo_modbus_input_5"] = er.RegistryEntry(
        entity_id="binary_sensor.elmo_modbus_input_5",
        unique_id="entry1:binary:alarm_input_5",
        platform=DOMAIN,
        config_entry_id="entry1",
    )

    call = SimpleNamespace(
        data={
            "entity_id": [
                "binary_sensor.elmo_modbus_input_3",
                "binary_sensor.elmo_modbus_input_5",
            ],
            services.ATTR_EXCLUDED: True,
        }
    )

    asyncio.run(services._async_handle_set_input_exclusion(hass, call))

    expected_addresses = {
        INPUT_SENSOR_EXCLUDED_START + 5 - 1,
        INPUT_SENSOR_EXCLUDED_START + 3 - 1,
    }

    assert {address for address, _ in inventory.writes} == expected_addresses
    assert all(value is False for _, value in inventory.writes)
    assert coordinator.refreshed


def test_async_handle_set_input_exclusion_accepts_legacy_entities() -> None:
    hass = HomeAssistant()
    inventory = DummyInventory()
    coordinator = DummyCoordinator()
    hass.data.setdefault(DOMAIN, {})["entry1"] = {
        "inventory": inventory,
        "coordinator": coordinator,
    }

    registry = er.async_get(hass)
    registry.entities["binary_sensor.elmo_modbus_input_7"] = er.RegistryEntry(
        entity_id="binary_sensor.elmo_modbus_input_7",
        unique_id="entry1:binary:alarm_input_7",
        platform=DOMAIN,
        config_entry_id="entry1",
    )

    call = SimpleNamespace(
        data={
            services.ATTR_INPUT_ENTITIES: [
                "binary_sensor.elmo_modbus_input_7",
            ],
            services.ATTR_EXCLUDED: False,
        }
    )

    asyncio.run(services._async_handle_set_input_exclusion(hass, call))

    expected_address = INPUT_SENSOR_EXCLUDED_START + 7 - 1

    assert inventory.writes == [(expected_address, True)]
    assert coordinator.refreshed