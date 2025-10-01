"""Data coordinator for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from .const import DEFAULT_SCAN_INTERVAL, REGISTER_STATUS_COUNT, REGISTER_STATUS_START

LOGGER = logging.getLogger(__name__)


class ElmoModbusCoordinator(DataUpdateCoordinator[list[bool]]):
    """Coordinator responsible for polling the Modbus control panel."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ModbusTcpClient,
        *,
        sector_count: int = REGISTER_STATUS_COUNT,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self._sector_count = max(1, min(sector_count, REGISTER_STATUS_COUNT))
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
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

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
        ordered = sorted({int(address) for address in addresses})
        self._addresses: tuple[int, ...] = tuple(ordered)
        groups: list[list[int]] = []
        current: list[int] = []
        for address in ordered:
            if not current or address == current[-1] + 1:
                current.append(address)
                continue
            groups.append(current)
            current = [address]
        if current:
            groups.append(current)

        self._groups: list[tuple[int, int, tuple[int, ...]]] = [
            (group[0], len(group), tuple(group)) for group in groups
        ]

    async def _async_update_data(self) -> dict[int, bool]:
        """Poll the Modbus device for diagnostic discrete inputs."""

        def _read_group(start: int, count: int) -> list[bool]:
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

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
        ordered = sorted({int(address) for address in addresses})
        self._addresses: tuple[int, ...] = tuple(ordered)
        groups: list[list[int]] = []
        current: list[int] = []
        for address in ordered:
            if not current or address == current[-1] + 1:
                current.append(address)
                continue
            groups.append(current)
            current = [address]
        if current:
            groups.append(current)

        self._groups: list[tuple[int, int, tuple[int, ...]]] = [
            (group[0], len(group), tuple(group)) for group in groups
        ]

    async def _async_update_data(self) -> dict[int, bool]:
        """Poll the Modbus device for output coil states."""

        def _read_group(start: int, count: int) -> list[bool]:
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

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
        ordered = sorted({int(address) for address in addresses})
        groups: list[list[int]] = []
        current: list[int] = []
        for address in ordered:
            if not current or address == current[-1] + 1:
                current.append(address)
                continue
            groups.append(current)
            current = [address]
        if current:
            groups.append(current)

        self._groups: list[tuple[int, int, tuple[int, ...]]] = [
            (group[0], len(group), tuple(group)) for group in groups
        ]

    async def _async_update_data(self) -> dict[int, int | None]:
        """Poll the Modbus device for holding registers."""

        def _read_group(start: int, count: int) -> list[int]:
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

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
