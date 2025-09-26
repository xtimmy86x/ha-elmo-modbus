"""Home Assistant integration for an Elmo Modbus alarm control panel."""

from __future__ import annotations

from typing import Any

from pymodbus.client import ModbusTcpClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import ElmoModbusCoordinator


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Elmo Modbus integration via YAML (not supported)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elmo Modbus from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = ModbusTcpClient(host=entry.data["host"], port=entry.data["port"])
    coordinator = ElmoModbusCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

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
        client: ModbusTcpClient = entry_data["client"]
        await hass.async_add_executor_job(client.close)

    return unload_ok

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates by reloading the config entry."""

    await hass.config_entries.async_reload(entry.entry_id)