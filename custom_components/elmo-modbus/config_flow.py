"""Config flow for the Elmo Modbus integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    OPTION_ARMED_AWAY_SECTORS,
    OPTION_ARMED_HOME_SECTORS,
    OPTION_ARMED_NIGHT_SECTORS,
    OPTION_DISARM_SECTORS,
    REGISTER_STATUS_COUNT,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=502): vol.All(int, vol.Range(min=1, max=65535)),
    }
)

OPTION_KEYS = [
    OPTION_ARMED_AWAY_SECTORS,
    OPTION_ARMED_HOME_SECTORS,
    OPTION_ARMED_NIGHT_SECTORS,
    OPTION_DISARM_SECTORS,
]


def _format_sector_list(sectors: list[int] | None) -> str:
    """Return a comma separated string suitable for the form defaults."""

    if not sectors:
        return ""
    return ", ".join(str(sector) for sector in sectors)


def _parse_sector_input(value: str) -> list[int]:
    """Parse the user provided string into a sorted list of valid sectors."""

    if not value:
        return []

    seen: set[int] = set()
    result: list[int] = []
    for part in (piece.strip() for piece in value.replace(";", ",").split(",")):
        if not part:
            continue
        try:
            sector = int(part)
        except ValueError as err:
            raise vol.Invalid("invalid_sector") from err

        if sector < 1 or sector > REGISTER_STATUS_COUNT:
            raise vol.Invalid("invalid_sector")
        if sector in seen:
            continue
        seen.add(sector)
        result.append(sector)

    return sorted(result)

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
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this config entry."""

        return ElmoModbusOptionsFlowHandler(config_entry)


class ElmoModbusOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow for configuring sector mappings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle the first step of the options flow."""

        return await self.async_step_user(user_input)

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Collect the sector mappings for each arming mode."""

        errors: dict[str, str] = {}
        if user_input is not None:
            options: dict[str, list[int]] = {}
            for key in OPTION_KEYS:
                try:
                    options[key] = _parse_sector_input(user_input.get(key, ""))
                except vol.Invalid:
                    errors[key] = "invalid_sector"

            if not errors:
                return self.async_create_entry(title="", data=options)

        current: dict[str, str] = {}
        if user_input is None:
            for key in OPTION_KEYS:
                current[key] = _format_sector_list(self._config_entry.options.get(key))
        else:
            for key in OPTION_KEYS:
                current[key] = user_input.get(key, "")

        data_schema = vol.Schema(
            {vol.Optional(key, default=current[key]): str for key in OPTION_KEYS}
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "max_sector": str(REGISTER_STATUS_COUNT),
            },
        )