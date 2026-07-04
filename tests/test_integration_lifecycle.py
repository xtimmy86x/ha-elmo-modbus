"""Tests for integration entry lifecycle behaviour."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

integration = importlib.import_module("custom_components.elmo_modbus")
HomeAssistant = importlib.import_module("homeassistant.core").HomeAssistant
DOMAIN = importlib.import_module("custom_components.elmo_modbus.const").DOMAIN


class _DummyCoordinator:
    def __init__(self) -> None:
        self.closed = False

    async def async_close(self) -> None:
        self.closed = True


def test_async_unload_entry_closes_connection_and_unloads_services(
    monkeypatch,
) -> None:
    """When the entry unloads successfully, coordinator connection is closed."""

    hass = HomeAssistant()
    coordinator = _DummyCoordinator()

    async def _async_unload_platforms(_entry, _platforms) -> bool:
        return True

    unload_services_called = False

    async def _async_unload_services(_hass) -> None:
        nonlocal unload_services_called
        unload_services_called = True

    monkeypatch.setattr(integration, "async_unload_services", _async_unload_services)

    hass.config_entries = SimpleNamespace(async_unload_platforms=_async_unload_platforms)
    hass.data = {
        DOMAIN: {
            "entry_1": {
                "inventory": object(),
                "coordinator": coordinator,
            }
        }
    }
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(integration.async_unload_entry(hass, entry))

    assert result is True
    assert coordinator.closed is True
    assert "entry_1" not in hass.data[DOMAIN]
    assert unload_services_called is True


def test_async_unload_entry_skips_close_when_platform_unload_fails() -> None:
    """Coordinator close is skipped if Home Assistant cannot unload platforms."""

    hass = HomeAssistant()
    coordinator = _DummyCoordinator()

    async def _async_unload_platforms(_entry, _platforms) -> bool:
        return False

    hass.config_entries = SimpleNamespace(async_unload_platforms=_async_unload_platforms)
    hass.data = {
        DOMAIN: {
            "entry_1": {
                "inventory": object(),
                "coordinator": coordinator,
            }
        }
    }
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(integration.async_unload_entry(hass, entry))

    assert result is False
    assert coordinator.closed is False
    assert "entry_1" in hass.data[DOMAIN]
