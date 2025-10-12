"""Home Assistant integration for an Elmo Modbus alarm control panel."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pymodbus.client import ModbusTcpClient

import logging
_LOGGER = logging.getLogger(__name__)

from .services import async_setup_services, async_unload_services
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SECTORS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SECTORS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ElmoModbusCoordinator, ElmoModbusInventory


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Elmo Modbus integration via YAML (not supported)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elmo Modbus from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = ModbusTcpClient(host=entry.data["host"], port=entry.data["port"])
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    sector_count = entry.data.get(CONF_SECTORS, DEFAULT_SECTORS)

    inventory = ElmoModbusInventory(client, sector_count=sector_count)
    inventory.require_status()

    coordinator = ElmoModbusCoordinator(
        hass,
        inventory,
        scan_interval=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "inventory": inventory,
        "coordinator": coordinator,
    }

    await async_setup_services(hass)
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Elmo Modbus config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data: dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator: ElmoModbusCoordinator = entry_data["coordinator"]
        await coordinator.async_close()

        await async_unload_services(hass)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates by reloading the config entry."""

    await hass.config_entries.async_reload(entry.entry_id)
