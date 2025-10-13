"""Data coordinator for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SECTORS,
    REGISTER_ALARM_START,
    REGISTER_STATUS_START,
)

_LOGGER = logging.getLogger(__name__)
_COORD_LOGGER = logging.getLogger(__name__ + ".coordinator_internal")

def _ensure_client_connected(client: ModbusTcpClient) -> None:
    """Ensure the Modbus client is connected before performing an operation."""

    if client.connected:
        return
    if not client.connect():
        raise ConnectionException("Unable to connect to Modbus device")

def _prepare_address_groups(
    addresses: Iterable[int],
) -> tuple[tuple[int, ...], tuple[tuple[int, int, tuple[int, ...]], ...]]:
    """Return a sorted tuple of addresses and grouped spans for Modbus reads."""

    ordered = tuple(sorted({int(address) for address in addresses}))
    if not ordered:
        return (), ()

    groups: list[tuple[int, int, tuple[int, ...]]] = []
    current: list[int] = [ordered[0]]

    for address in ordered[1:]:
        if address == current[-1] + 1:
            current.append(address)
            continue
        groups.append((current[0], len(current), tuple(current)))
        current = [address]

    groups.append((current[0], len(current), tuple(current)))

    return ordered, tuple(groups)


@dataclass(frozen=True)
class ElmoPanelStatus:
    """Structured representation of the panel arming and alarm status."""

    armed: tuple[bool, ...]
    triggered: tuple[bool, ...]


@dataclass(frozen=True)
class ElmoInventorySnapshot:
    """Representation of the cached state held by the Modbus inventory."""

    status: ElmoPanelStatus | None
    discrete_inputs: dict[int, bool]
    coils: dict[int, bool]
    holding_registers: dict[int, int | None]


class ElmoModbusInventory:
    """Book-keeping of addresses polled from the Modbus device."""

    def __init__(self, client: ModbusTcpClient, *, sector_count: int) -> None:
        self._client = client
        self._sector_count = max(1, min(sector_count, DEFAULT_SECTORS))
        self._status_required = False
        self._discrete_inputs: set[int] = set()
        self._coils: set[int] = set()
        self._holding_registers: set[int] = set()
        self._cached_status: ElmoPanelStatus | None = None
        self._cached_inputs: dict[int, bool] = {}
        self._cached_coils: dict[int, bool] = {}
        self._cached_registers: dict[int, int | None] = {}

    @property
    def sector_count(self) -> int:
        """Return the number of sectors managed by the inventory."""

        return self._sector_count

    def require_status(self) -> bool:
        """Ensure the arming and alarm status registers are polled."""

        if self._status_required:
            return False
        self._status_required = True
        return True

    def add_discrete_inputs(self, addresses: Iterable[int]) -> bool:
        """Register additional discrete input addresses for polling."""

        before = set(self._discrete_inputs)
        for address in addresses:
            try:
                value = int(address)
            except (TypeError, ValueError):
                continue
            self._discrete_inputs.add(value)
        return before != self._discrete_inputs

    def add_coils(self, addresses: Iterable[int]) -> bool:
        """Register additional coil addresses for polling."""

        before = set(self._coils)
        for address in addresses:
            try:
                value = int(address)
            except (TypeError, ValueError):
                continue
            self._coils.add(value)
        return before != self._coils

    def add_holding_registers(self, addresses: Iterable[int]) -> bool:
        """Register additional holding register addresses for polling."""

        before = set(self._holding_registers)
        for address in addresses:
            try:
                value = int(address)
            except (TypeError, ValueError):
                continue
            self._holding_registers.add(value)
        return before != self._holding_registers

    def refresh(self) -> ElmoInventorySnapshot:
        """Poll the Modbus device for all registered addresses."""

        status = self._cached_status
        discrete_inputs = dict(self._cached_inputs)
        coils = dict(self._cached_coils)
        holding_registers = dict(self._cached_registers)

        if self._status_required:
            status = self._read_status()
            self._cached_status = status

        if self._discrete_inputs:
            discrete_inputs = self._read_discrete_inputs()
            self._cached_inputs = discrete_inputs

        if self._coils:
            coils = self._read_coils()
            self._cached_coils = coils

        if self._holding_registers:
            holding_registers = self._read_holding_registers()
            self._cached_registers = holding_registers

        return ElmoInventorySnapshot(
            status=status,
            discrete_inputs=dict(discrete_inputs),
            coils=dict(coils),
            holding_registers=dict(holding_registers),
        )

    def _read_status(self) -> ElmoPanelStatus:
        """Read the arming and alarm status spans."""

        def _read_span(start: int) -> tuple[bool, ...]:
            _ensure_client_connected(self._client)

            response = self._client.read_discrete_inputs(start, count=self._sector_count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            return tuple(bool(bit) for bit in bits[: self._sector_count])

        armed_bits = _read_span(REGISTER_STATUS_START)
        triggered_bits = _read_span(REGISTER_ALARM_START)
        return ElmoPanelStatus(armed=armed_bits, triggered=triggered_bits)

    def _read_discrete_inputs(self) -> dict[int, bool]:
        """Read all registered discrete input addresses."""

        _, groups = _prepare_address_groups(self._discrete_inputs)
        results: dict[int, bool] = {}

        for start, count, addresses in groups:
            _ensure_client_connected(self._client)
            response = self._client.read_discrete_inputs(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            for index, address in enumerate(addresses):
                results[address] = bool(bits[index]) if index < len(bits) else False

        return results

    def _read_coils(self) -> dict[int, bool]:
        """Read all registered coil addresses."""

        _, groups = _prepare_address_groups(self._coils)
        results: dict[int, bool] = {}

        for start, count, addresses in groups:
            _ensure_client_connected(self._client)
            response = self._client.read_coils(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            for index, address in enumerate(addresses):
                results[address] = bool(bits[index]) if index < len(bits) else False

        return results

    def _read_holding_registers(self) -> dict[int, int | None]:
        """Read all registered holding register addresses."""

        _, groups = _prepare_address_groups(self._holding_registers)
        results: dict[int, int | None] = {}

        for start, count, addresses in groups:
            _ensure_client_connected(self._client)
            response = self._client.read_holding_registers(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            registers: list[int] = list(getattr(response, "registers", []) or [])
            for index, address in enumerate(addresses):
                results[address] = registers[index] if index < len(registers) else None

        return results

    def write_coil(self, address: int, value: bool) -> None:
        """Write a single coil and update the cached value."""

        address = int(address)
        _ensure_client_connected(self._client)
        response = self._client.write_coil(address, value)
        if not response or getattr(response, "isError", lambda: True)():
            raise ConnectionException("Invalid response when writing coil")
        self._cached_coils[address] = bool(value)

    def write_coils(self, start: int, values: Sequence[bool]) -> None:
        """Write a sequence of coils and update cached values when tracked."""

        payload = [bool(value) for value in values]
        if not payload:
            return

        _ensure_client_connected(self._client)
        response = self._client.write_coils(start, payload)
        if not response or getattr(response, "isError", lambda: True)():
            raise ConnectionException("Invalid response when writing coils")

        for offset, value in enumerate(payload):
            address = start + offset
            if address in self._coils or address in self._cached_coils:
                self._cached_coils[address] = bool(value)

    def close(self) -> None:
        """Close the underlying Modbus client connection."""

        if self._client.connected:
            self._client.close()


class ElmoModbusCoordinator(DataUpdateCoordinator[ElmoInventorySnapshot]):
    """Coordinator responsible for polling the Modbus inventory."""

    def __init__(
        self,
        hass: HomeAssistant,
        inventory: ElmoModbusInventory,
        *,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self._inventory = inventory
        super().__init__(
            hass,
            _COORD_LOGGER,
            name="Elmo Modbus inventory",
            update_interval=timedelta(seconds=max(1, scan_interval)),
        )

    @property
    def inventory(self) -> ElmoModbusInventory:
        """Return the underlying inventory."""

        return self._inventory

    @property
    def sector_count(self) -> int:
        """Expose the inventory sector count for entities."""

        return self._inventory.sector_count

    async def _async_update_data(self) -> ElmoInventorySnapshot:
        """Poll the Modbus device via the shared inventory."""
        
        try:
            return await self.hass.async_add_executor_job(self._inventory.refresh)
        except ConnectionException as err:
            raise UpdateFailed(f"Modbus connection failed: {err}") from err
        except Exception as err:  # pragma: no cover - safety net for unexpected errors
            raise UpdateFailed(f"Unexpected Modbus error: {err}") from err

    async def async_close(self) -> None:
        """Close the underlying Modbus client connection."""

        await self.hass.async_add_executor_job(self._inventory.close)
