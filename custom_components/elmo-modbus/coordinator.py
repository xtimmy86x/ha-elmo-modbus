"""Data coordinator for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_SECTORS, REGISTER_STATUS_START

LOGGER = logging.getLogger(__name__)


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


class ElmoModbusCoordinator(DataUpdateCoordinator[list[bool]]):
    """Coordinator responsible for polling the Modbus control panel."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ModbusTcpClient,
        *,
        sector_count: int = DEFAULT_SECTORS,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self._sector_count = max(1, min(sector_count, DEFAULT_SECTORS))
        super().__init__(
            hass,
            LOGGER,
            name="Elmo Modbus status",
            update_interval=timedelta(seconds=max(1, scan_interval)),
        )
        self._client = client

    async def _async_update_data(self) -> list[bool]:
        """Poll the Modbus device for the per-sector arming status bits."""

        def _read_status() -> list[bool]:
            """Synchronously read the discrete inputs from the device."""
            _ensure_client_connected(self._client)

            response = self._client.read_discrete_inputs(
                REGISTER_STATUS_START, count=self._sector_count
            )
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            # The pymodbus response may include more bits than requested when the
            # count isn't a multiple of eight. Trim the list to the exact span we
            # asked for to avoid leaking stale states.
            return bits[: self._sector_count]

        try:
            return await self.hass.async_add_executor_job(_read_status)
        except ConnectionException as err:
            raise UpdateFailed(f"Modbus connection failed: {err}") from err
        except Exception as err:  # pragma: no cover - safety net for unexpected errors
            raise UpdateFailed(f"Unexpected Modbus error: {err}") from err

    async def async_close(self) -> None:
        """Close the underlying Modbus client connection."""

        def _close() -> None:
            if self._client.connected:
                self._client.close()

        await self.hass.async_add_executor_job(_close)

    @property
    def sector_count(self) -> int:
        """Return the number of sectors handled by this coordinator."""

        return self._sector_count


class ElmoModbusBinarySensorCoordinator(DataUpdateCoordinator[dict[int, bool]]):
    """Coordinator for reading discrete inputs used by diagnostic binary sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ModbusTcpClient,
        *,
        addresses: Iterable[int],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialise the diagnostic coordinator."""

        super().__init__(
            hass,
            LOGGER,
            name="Elmo Modbus diagnostics",
            update_interval=timedelta(seconds=max(1, scan_interval)),
        )
        self._client = client
        ordered, groups = _prepare_address_groups(addresses)
        self._addresses: tuple[int, ...] = ordered
        self._groups: list[tuple[int, int, tuple[int, ...]]] = list(groups)

    async def _async_update_data(self) -> dict[int, bool]:
        """Poll the Modbus device for diagnostic discrete inputs."""

        def _read_group(start: int, count: int) -> list[bool]:
            _ensure_client_connected(self._client)

            response = self._client.read_discrete_inputs(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            return bits[:count]

        results: dict[int, bool] = {}

        try:
            for start, count, addresses in self._groups:
                bits = await self.hass.async_add_executor_job(_read_group, start, count)
                for index, address in enumerate(addresses):
                    results[address] = bool(bits[index]) if index < len(bits) else False
            return results
        except ConnectionException as err:
            raise UpdateFailed(f"Modbus connection failed: {err}") from err
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(f"Unexpected Modbus error: {err}") from err

    @property
    def addresses(self) -> tuple[int, ...]:
        """Return the discrete input addresses polled by the coordinator."""

        return self._addresses


class ElmoModbusSwitchCoordinator(DataUpdateCoordinator[dict[int, bool]]):
    """Coordinator for reading and tracking output coil states."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ModbusTcpClient,
        *,
        addresses: Iterable[int],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialise the output coordinator."""

        super().__init__(
            hass,
            LOGGER,
            name="Elmo Modbus outputs",
            update_interval=timedelta(seconds=max(1, scan_interval)),
        )
        self._client = client
        ordered, groups = _prepare_address_groups(addresses)
        self._addresses = ordered
        self._groups = list(groups)

    async def _async_update_data(self) -> dict[int, bool]:
        """Poll the Modbus device for output coil states."""

        def _read_group(start: int, count: int) -> list[bool]:
            _ensure_client_connected(self._client)

            response = self._client.read_coils(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            bits: list[bool] = list(response.bits)
            return bits[:count]

        results: dict[int, bool] = {}

        try:
            for start, count, addresses in self._groups:
                bits = await self.hass.async_add_executor_job(_read_group, start, count)
                for index, address in enumerate(addresses):
                    results[address] = bool(bits[index]) if index < len(bits) else False
            return results
        except ConnectionException as err:
            raise UpdateFailed(f"Modbus connection failed: {err}") from err
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(f"Unexpected Modbus error: {err}") from err

    @property
    def addresses(self) -> tuple[int, ...]:
        """Return the coil addresses polled by the coordinator."""

        return self._addresses


class ElmoModbusSensorCoordinator(DataUpdateCoordinator[dict[int, int | None]]):
    """Coordinator for reading holding registers exposed as sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ModbusTcpClient,
        *,
        addresses: Iterable[int],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialise the sensor coordinator."""

        super().__init__(
            hass,
            LOGGER,
            name="Elmo Modbus sensors",
            update_interval=timedelta(seconds=max(1, scan_interval)),
        )
        self._client = client
        _, groups = _prepare_address_groups(addresses)
        self._groups = list(groups)

    async def _async_update_data(self) -> dict[int, int | None]:
        """Poll the Modbus device for holding registers."""

        def _read_group(start: int, count: int) -> list[int]:
            _ensure_client_connected(self._client)

            response = self._client.read_holding_registers(start, count=count)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            registers: list[int] = list(getattr(response, "registers", []) or [])
            return registers[:count]

        results: dict[int, int | None] = {}

        try:
            for start, count, addresses in self._groups:
                registers = await self.hass.async_add_executor_job(
                    _read_group, start, count
                )
                for index, address in enumerate(addresses):
                    results[address] = (
                        registers[index] if index < len(registers) else None
                    )
            return results
        except ConnectionException as err:
            raise UpdateFailed(f"Modbus connection failed: {err}") from err
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(f"Unexpected Modbus error: {err}") from err
