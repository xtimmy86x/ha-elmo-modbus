"""Config flow for the Elmo Modbus integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import DOMAIN, OPTION_USER_CODES, REGISTER_STATUS_COUNT
from .panels import MODES, load_panel_definitions, panels_to_options

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=502): vol.All(int, vol.Range(min=1, max=65535)),
    }
)

MENU_OPTION_PANELS = "panels"
MENU_OPTION_ADD_PANEL = "add_panel"
MENU_OPTION_USER_CODES = "user_codes"
MENU_OPTION_FINISH = "finish"


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


def _format_user_codes(codes: list[str] | None) -> str:
    """Return a newline separated string suitable for the form defaults."""

    if not codes:
        return ""
    return "\n".join(codes)


def _parse_user_code_input(value: str) -> list[str]:
    """Parse the user provided codes into a normalised list."""

    if not value:
        return []

    seen: set[str] = set()
    result: list[str] = []

    for raw_code in value.splitlines():
        code = raw_code.strip()
        if not code:
            continue
        if code in seen:
            raise vol.Invalid("duplicate_code")
        seen.add(code)
        result.append(code)

    return result


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
        definitions = load_panel_definitions(config_entry.options)
        self._panels: list[dict[str, Any]] = []
        for panel in definitions:
            modes: dict[str, list[int]] = {}
            for mode in MODES:
                sectors = sorted(panel.mode_sectors(mode))
                if sectors:
                    modes[mode] = sectors
            self._panels.append(
                {
                    "name": panel.name,
                    "entity_id_suffix": panel.slug,
                    "modes": modes,
                }
            )

        raw_codes = config_entry.options.get(OPTION_USER_CODES, [])
        self._user_codes: list[str] = []
        if isinstance(raw_codes, list):
            for code in raw_codes:
                if isinstance(code, str) and code.strip():
                    self._user_codes.append(code.strip())

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Display the options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options={
                MENU_OPTION_PANELS: "panels",
                MENU_OPTION_ADD_PANEL: "add_panel",
                MENU_OPTION_USER_CODES: "user_codes",
                MENU_OPTION_FINISH: "finish",
            },
        )

    async def async_step_add_panel(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a new panel with default values and open the panel editor."""

        self._panels.append(
            {
                "name": f"Panel {len(self._panels) + 1}",
                "entity_id_suffix": "",
                "modes": {},
            }
        )
        return await self.async_step_panels()

    def _panel_defaults(
        self, index: int, user_input: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Return default values for the form based on the current panel state."""

        panel = self._panels[index]
        prefix = f"panel_{index}_"
        defaults: dict[str, Any] = {}

        if user_input is not None:
            defaults["name"] = user_input.get(
                f"{prefix}name", panel.get("name", f"Panel {index + 1}")
            )
            defaults["entity_id_suffix"] = user_input.get(
                f"{prefix}entity_id_suffix", panel.get("entity_id_suffix", "")
            )
            defaults["remove"] = bool(user_input.get(f"{prefix}remove", False))
            for mode in MODES:
                defaults[mode] = user_input.get(
                    f"{prefix}{mode}",
                    _format_sector_list(panel.get("modes", {}).get(mode)),
                )
        else:
            defaults["name"] = panel.get("name", f"Panel {index + 1}")
            defaults["entity_id_suffix"] = panel.get("entity_id_suffix", "")
            defaults["remove"] = False
            for mode in MODES:
                defaults[mode] = _format_sector_list(panel.get("modes", {}).get(mode))

        return defaults

    def _build_schema(
        self, user_input: dict[str, Any] | None
    ) -> vol.Schema:
        """Build the form schema for the current panel list."""

        schema: dict[Any, Any] = {}
        for index, _ in enumerate(self._panels):
            defaults = self._panel_defaults(index, user_input)
            prefix = f"panel_{index}_"
            schema[vol.Required(f"{prefix}name", default=defaults["name"])] = str
            schema[
                vol.Optional(
                    f"{prefix}entity_id_suffix", default=defaults["entity_id_suffix"]
                )
            ] = str
            for mode in MODES:
                schema[
                    vol.Optional(f"{prefix}{mode}", default=defaults[mode])
                ] = str
            schema[vol.Optional(f"{prefix}remove", default=defaults["remove"])] = bool


        return vol.Schema(schema)

    def _show_panel_form(
        self,
        *,
        errors: dict[str, str] | None = None,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Return the options form."""

        return self.async_show_form(
            step_id="panels",
            data_schema=self._build_schema(user_input),
            errors=errors or {},
            description_placeholders={
                "max_sector": str(REGISTER_STATUS_COUNT),
            },
        )

    async def async_step_panels(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect the sector mappings for each arming mode."""

        errors: dict[str, str] = {}
        if user_input is not None:
            updated_panels: list[dict[str, Any]] = []
            for index, panel in enumerate(self._panels):
                prefix = f"panel_{index}_"
                if user_input.get(f"{prefix}remove"):
                    continue

                name_input = (user_input.get(f"{prefix}name") or "").strip()
                if not name_input:
                    errors[f"{prefix}name"] = "required"
                name_value = name_input or panel.get("name", f"Panel {index + 1}")

                slug_input = (user_input.get(f"{prefix}entity_id_suffix") or "").strip()
                slug_candidate = slugify(slug_input) if slug_input else slugify(name_value)
                if not slug_candidate:
                    errors[f"{prefix}entity_id_suffix"] = "invalid_slug"
                    slug_candidate = slugify(panel.get("entity_id_suffix") or name_value) or f"panel_{index + 1}"

                modes: dict[str, list[int]] = {}
                for mode in MODES:
                    field = f"{prefix}{mode}"
                    try:
                        sectors = _parse_sector_input(user_input.get(field, ""))
                    except vol.Invalid:
                        errors[field] = "invalid_sector"
                        sectors = panel.get("modes", {}).get(mode, [])
                    if sectors:
                        modes[mode] = sectors

                updated_panels.append(
                    {
                        "name": name_value,
                        "entity_id_suffix": slug_candidate,
                        "modes": modes,
                    }
                )

            # Ensure unique slugs across the updated panel set.
            slug_seen: dict[str, int] = {}
            for index, panel in enumerate(updated_panels):
                slug_value = slugify(panel.get("entity_id_suffix") or panel["name"])
                if not slug_value:
                    slug_value = f"panel_{index + 1}"
                if slug_value in slug_seen:
                    errors[f"panel_{index}_entity_id_suffix"] = "duplicate_slug"
                    errors[f"panel_{slug_seen[slug_value]}_entity_id_suffix"] = "duplicate_slug"
                else:
                    slug_seen[slug_value] = index
                panel["entity_id_suffix"] = slug_value

            if errors:
                self._panels = updated_panels
                return self._show_panel_form(errors=errors, user_input=user_input)

            self._panels = updated_panels
            return await self.async_step_init()

        return self._show_panel_form()

    async def async_step_user_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure one or more user codes for the alarm panels."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                codes = _parse_user_code_input(user_input.get("codes", ""))
            except vol.Invalid as err:
                errors["codes"] = err.error_message or "invalid_code"
            else:
                self._user_codes = codes
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    "codes",
                    default=_format_user_codes(self._user_codes),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                )
            }
        )

        return self.async_show_form(
            step_id="user_codes",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Persist the configured options and close the flow."""

        options = panels_to_options(self._panels)
        options[OPTION_USER_CODES] = list(self._user_codes)
        return self.async_create_entry(title="", data=options)