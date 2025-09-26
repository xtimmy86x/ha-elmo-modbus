"""Config flow for the Elmo Modbus integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=502): vol.All(int, vol.Range(min=1, max=65535)),
    }
)


class ElmoModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for the Elmo Modbus integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Handle the initial step where the user enters connection details."""
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input['host']}:{user_input['port']}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=user_input["host"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)