"""Data coordinator for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from .const import (
    DEFAULT_SCAN_INTERVAL,
    REGISTER_STATUS_COUNT,
    REGISTER_STATUS_START,
)

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
    