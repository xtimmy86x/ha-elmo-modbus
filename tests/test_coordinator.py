"""Tests for Modbus coordinator reconnect behaviour."""

from __future__ import annotations

import asyncio
import importlib

import pytest

HomeAssistant = importlib.import_module("homeassistant.core").HomeAssistant
UpdateFailed = importlib.import_module(
    "homeassistant.helpers.update_coordinator"
).UpdateFailed

coordinator_module = importlib.import_module("custom_components.elmo_modbus.coordinator")
ElmoModbusCoordinator = coordinator_module.ElmoModbusCoordinator
ElmoModbusInventory = coordinator_module.ElmoModbusInventory
ElmoInventorySnapshot = coordinator_module.ElmoInventorySnapshot


class _ReadResponse:
    def __init__(self, bits: list[bool]) -> None:
        self.bits = bits

    def isError(self) -> bool:
        return False


class _FlakyClient:
    def __init__(self) -> None:
        self.connected = True
        self.connect_calls = 0
        self.close_calls = 0
        self.fail_reads = 1

    def connect(self) -> bool:
        self.connect_calls += 1
        self.connected = True
        return True

    def close(self) -> None:
        self.close_calls += 1
        self.connected = False

    def read_discrete_inputs(self, _start: int, count: int) -> _ReadResponse:
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise RuntimeError("No response received after 3 retries")
        return _ReadResponse([False] * count)


def test_coordinator_resets_and_reconnects_after_poll_error() -> None:
    """A failed poll should close the socket and reconnect on next update."""

    hass = HomeAssistant()
    client = _FlakyClient()
    inventory = ElmoModbusInventory(client, sector_count=1)
    inventory.require_status()
    coordinator = ElmoModbusCoordinator(hass, inventory, scan_interval=10)

    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator._async_update_data())

    assert client.close_calls == 1
    assert client.connected is False

    snapshot = asyncio.run(coordinator._async_update_data())

    assert isinstance(snapshot, ElmoInventorySnapshot)
    assert client.connect_calls == 1
    assert client.connected is True
