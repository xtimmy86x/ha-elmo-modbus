"""Data coordinator for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, REGISTER_STATUS

LOGGER = logging.getLogger(__name__)


class ElmoModbusCoordinator(DataUpdateCoordinator[int]):
    """Coordinator responsible for polling the Modbus control panel."""

    def __init__(self, hass: HomeAssistant, client: ModbusTcpClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="Elmo Modbus status",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._client = client

    async def _async_update_data(self) -> int:
        """Poll the Modbus device for the alarm status register."""

        def _read_status() -> int:
            """Synchronously read the status register from the device."""
            if not self._client.connected:
                if not self._client.connect():
                    raise ConnectionException("Unable to connect to Modbus device")

            response = self._client.read_holding_registers(REGISTER_STATUS, 1)
            if not response or getattr(response, "isError", lambda: True)():
                raise ConnectionException("Invalid response when reading register")

            return response.registers[0]

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