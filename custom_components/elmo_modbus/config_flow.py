"""Config flow for the Elmo Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import slugify

from .const import (
    CONF_INPUT_SENSORS,
    CONF_OUTPUT_SWITCHES,
    CONF_SCAN_INTERVAL,
    CONF_SECTORS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SECTORS,
    DOMAIN,
    INOUT_MAX_COUNT,
    OPTION_INPUT_NAMES,
    OPTION_OUTPUT_NAMES,
    OPTION_USER_CODES,
)
from .input_selectors import (
    format_input_sensor_list,
    normalize_input_sensor_config,
    parse_input_sensor_selection,
)
from .panels import MODES, load_panel_definitions, panels_to_options

DEFAULT_PORT = 502

_LOGGER = logging.getLogger(__name__)


async def _async_input_name_templates(
    hass: HomeAssistant,
) -> tuple[str, str]:
    """Return templates for default input names and titles.

    The Home Assistant translation API is relatively expensive, therefore the
    templates are fetched once per flow and reused when building the form.
    """

    try:
        translations = await async_get_translations(
            hass,
            language=hass.config.language,
            category="options",
            integrations={DOMAIN},
            config_flow=True,
        )
    except Exception:  # pragma: no cover - defensive, HA handles logging
        _LOGGER.debug("Falling back to default input name templates", exc_info=True)
        return "Alarm input {number}", "Name of alarm input"

    base_key = f"component.{DOMAIN}.options.step.input_names.data.{{}}"
    default_template = translations.get(
        base_key.format("default_input_name"), "Alarm input {number}"
    )
    title_template = translations.get(
        base_key.format("pre_title"), "Name of alarm input"
    )
    return str(default_template), str(title_template)


async def _async_output_name_templates(
    hass: HomeAssistant,
) -> tuple[str, str]:
    """Return templates for default output names and titles."""

    try:
        translations = await async_get_translations(
            hass,
            language=hass.config.language,
            category="options",
            integrations={DOMAIN},
            config_flow=True,
        )
    except Exception:  # pragma: no cover - defensive, HA handles logging
        _LOGGER.debug("Falling back to default output name templates", exc_info=True)
        return "Output {number}", "Name of output"

    base_key = f"component.{DOMAIN}.options.step.output_names.data.{{}}"
    default_template = translations.get(
        base_key.format("default_output_name"), "Output {number}"
    )
    title_template = translations.get(base_key.format("pre_title"), "Name of output")
    return str(default_template), str(title_template)


def _format_with_number(template: str, number: int) -> str:
    """Format a translation template, ignoring missing placeholders."""

    try:
        return template.format(number=number)
    except (KeyError, IndexError, ValueError):
        return template


def _user_step_schema(
    name: str = DEFAULT_NAME,
    host: str = "",
    port: int = DEFAULT_PORT,
    *,
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    sectors: int = DEFAULT_SECTORS,
) -> vol.Schema:
    """Return the schema for the initial configuration step."""

    return vol.Schema(
        {
            vol.Required("name", default=name or DEFAULT_NAME): str,
            vol.Required("host", default=host): str,
            vol.Required("port", default=port): vol.All(
                int, vol.Range(min=1, max=65535)
            ),
            vol.Required("scan_interval", default=scan_interval): vol.All(
                int, vol.Range(min=1, max=3600)
            ),
            vol.Required("sectors", default=sectors): vol.All(
                int, vol.Range(min=1, max=DEFAULT_SECTORS)
            ),
        }
    )


DATA_SCHEMA = _user_step_schema()

MENU_OPTION_CONFIG = "config"
MENU_OPTION_INPUTS = "inputs"
MENU_OPTION_OUTPUTS = "outputs"
MENU_OPTION_PANELS = "panels"
MENU_OPTION_ADD_PANEL = "add_panel"
MENU_OPTION_USER_CODES = "user_codes"


def _format_sector_list(sectors: list[int] | None) -> str:
    """Return a comma separated string suitable for the form defaults."""

    if not sectors:
        return ""
    return ", ".join(str(sector) for sector in sectors)


def _parse_sector_input(value: str, *, max_sector: int) -> list[int]:
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

        if sector < 1 or sector > max_sector:
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

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle the initial step where the user enters connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_name = (user_input.get("name") or "").strip()
            raw_host = (user_input.get("host") or "").strip()
            port = user_input.get("port", DEFAULT_PORT)
            scan_interval = user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            sectors = user_input.get("sectors", DEFAULT_SECTORS)

            if not raw_host:
                errors["host"] = "required"

            name = raw_name or DEFAULT_NAME

            if errors:
                schema = _user_step_schema(
                    name=raw_name or DEFAULT_NAME,
                    host=user_input.get("host", ""),
                    port=port,
                    scan_interval=scan_interval,
                    sectors=sectors,
                )
                return self.async_show_form(
                    step_id="user",
                    data_schema=schema,
                    errors=errors,
                )

            await self.async_set_unique_id(f"{raw_host}:{port}")
            self._abort_if_unique_id_configured()

            data = {
                "name": name,
                "host": raw_host,
                "port": port,
                CONF_SCAN_INTERVAL: scan_interval,
                CONF_SECTORS: sectors,
            }
            _LOGGER.debug("Creating config entry with data: %s", data)
            return self.async_create_entry(
                title=name,
                data=data,
            )

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
        sector_limit = int(config_entry.data.get(CONF_SECTORS, DEFAULT_SECTORS))
        self._sector_limit = max(1, min(sector_limit, DEFAULT_SECTORS))
        definitions = load_panel_definitions(
            config_entry.options, max_sector=self._sector_limit
        )
        self._panels: list[dict[str, Any]] = []
        self._panel_index: int | None = None
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

        self._input_sensor_ids: list[int] = normalize_input_sensor_config(
            config_entry.options.get(CONF_INPUT_SENSORS),
            max_input=INOUT_MAX_COUNT,
        )
        if not self._input_sensor_ids and CONF_INPUT_SENSORS in config_entry.data:
            self._input_sensor_ids = normalize_input_sensor_config(
                config_entry.data.get(CONF_INPUT_SENSORS),
                max_input=INOUT_MAX_COUNT,
            )

        raw_names = config_entry.options.get(OPTION_INPUT_NAMES, {})
        self._input_names: dict[str, str] = {}
        if isinstance(raw_names, dict):
            for key, value in raw_names.items():
                try:
                    sensor = int(key)
                except (TypeError, ValueError):
                    continue
                if sensor not in self._input_sensor_ids:
                    continue
                name = str(value).strip()
                if name:
                    self._input_names[str(sensor)] = name

        self._pending_input_sensor_ids: list[int] | None = None
        self._input_name_templates: tuple[str, str] | None = None
        # ``self.hass`` is not available when the options flow handler is
        # constructed. The active language is captured the first time the
        # input naming step runs instead.
        self._input_name_language: str | None = None

        self._output_switch_ids: list[int] = normalize_input_sensor_config(
            config_entry.options.get(CONF_OUTPUT_SWITCHES),
            max_input=INOUT_MAX_COUNT,
        )
        if not self._output_switch_ids and CONF_OUTPUT_SWITCHES in config_entry.data:
            self._output_switch_ids = normalize_input_sensor_config(
                config_entry.data.get(CONF_OUTPUT_SWITCHES),
                max_input=INOUT_MAX_COUNT,
            )

        raw_output_names = config_entry.options.get(OPTION_OUTPUT_NAMES, {})
        self._output_names: dict[str, str] = {}
        if isinstance(raw_output_names, dict):
            for key, value in raw_output_names.items():
                try:
                    output = int(key)
                except (TypeError, ValueError):
                    continue
                if output not in self._output_switch_ids:
                    continue
                name = str(value).strip()
                if name:
                    self._output_names[str(output)] = name

        self._pending_output_switch_ids: list[int] | None = None
        self._output_name_templates: tuple[str, str] | None = None
        self._output_name_language: str | None = None

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Display the options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options={
                MENU_OPTION_CONFIG,
                MENU_OPTION_INPUTS,
                MENU_OPTION_OUTPUTS,
                MENU_OPTION_PANELS,
                MENU_OPTION_ADD_PANEL,
                MENU_OPTION_USER_CODES,
            },
        )

    async def async_step_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit the core configuration values for the integration."""

        current_data = self._config_entry.data
        default_name = current_data.get("name", DEFAULT_NAME)
        default_host = current_data.get("host", "")
        default_port = current_data.get("port", DEFAULT_PORT)
        default_scan = current_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        default_sectors = current_data.get(CONF_SECTORS, self._sector_limit)
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_name = (user_input.get("name") or "").strip()
            raw_host = (user_input.get("host") or "").strip()
            port = user_input.get("port", DEFAULT_PORT)
            scan_interval = user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            sectors = user_input.get("sectors", default_sectors)

            if not raw_host:
                errors["host"] = "required"

            name = raw_name or DEFAULT_NAME

            unique_id = f"{raw_host}:{port}"
            if not errors and unique_id != self._config_entry.unique_id:
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        entry.unique_id == unique_id
                        and entry.entry_id != self._config_entry.entry_id
                    ):
                        errors["base"] = "already_configured"
                        break

            if not errors:
                new_data = {
                    "name": name,
                    "host": raw_host,
                    "port": port,
                    CONF_SCAN_INTERVAL: scan_interval,
                    CONF_SECTORS: sectors,
                }

                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                    title=name,
                    unique_id=unique_id,
                )

                sector_limit = max(1, min(sectors, DEFAULT_SECTORS))
                if sector_limit != self._sector_limit:
                    for panel in self._panels:
                        sanitized_modes: dict[str, list[int]] = {}
                        for mode, values in panel.get("modes", {}).items():
                            valid = sorted(
                                {
                                    sector
                                    for sector in values
                                    if isinstance(sector, int)
                                    and 1 <= sector <= sector_limit
                                }
                            )
                            if valid:
                                sanitized_modes[mode] = valid
                        panel["modes"] = sanitized_modes

                    self._sector_limit = sector_limit
                    self._update_config_entry_options()
                else:
                    self._sector_limit = sector_limit

                return await self.async_step_init()

            schema = _user_step_schema(
                name=raw_name,
                host=raw_host,
                port=port,
                scan_interval=scan_interval,
                sectors=sectors,
            )
        else:
            schema = _user_step_schema(
                name=default_name,
                host=default_host,
                port=default_port,
                scan_interval=default_scan,
                sectors=default_sectors,
            )

        return self.async_show_form(
            step_id="config",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_inputs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure which alarm inputs should be monitored."""

        if self._input_sensor_ids:
            default_inputs = list(self._input_sensor_ids)
        elif CONF_INPUT_SENSORS in self._config_entry.data:
            default_inputs = normalize_input_sensor_config(
                self._config_entry.data.get(CONF_INPUT_SENSORS),
                max_input=INOUT_MAX_COUNT,
            )
        else:
            default_inputs = []
        default_count = len(default_inputs)
        default_value = format_input_sensor_list(default_inputs)

        errors: dict[str, str] = {}

        if user_input is not None:
            count = user_input.get("count", default_count)
            raw_selection = user_input.get(CONF_INPUT_SENSORS, "")

            if count == 0:
                if raw_selection and raw_selection.strip():
                    errors[CONF_INPUT_SENSORS] = "invalid_input"
                else:
                    self._input_sensor_ids = []
                    self._input_names = {}
                    self._pending_input_sensor_ids = None
                    self._update_config_entry_options()
                    return await self.async_step_init()
            else:
                try:
                    inputs = parse_input_sensor_selection(
                        raw_selection, max_input=INOUT_MAX_COUNT
                    )
                except ValueError:
                    errors[CONF_INPUT_SENSORS] = "invalid_input"
                    inputs = default_inputs
                else:
                    if len(inputs) != count:
                        errors["count"] = "input_count_mismatch"

                if not errors:
                    self._pending_input_sensor_ids = inputs
                    self._retain_input_names(inputs)
                    return await self.async_step_input_names()

            schema = vol.Schema(
                {
                    vol.Required("count", default=count): vol.All(
                        int, vol.Range(min=0, max=INOUT_MAX_COUNT)
                    ),
                    vol.Optional(
                        CONF_INPUT_SENSORS,
                        default=raw_selection,
                    ): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("count", default=default_count): vol.All(
                        int, vol.Range(min=0, max=INOUT_MAX_COUNT)
                    ),
                    vol.Optional(CONF_INPUT_SENSORS, default=default_value): str,
                }
            )

        return self.async_show_form(
            step_id="inputs",
            data_schema=schema,
            errors=errors,
            description_placeholders={"max_input": str(INOUT_MAX_COUNT)},
        )

    async def async_step_input_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Assign names to each configured alarm input."""

        sensor_ids = self._pending_input_sensor_ids or self._input_sensor_ids
        if not sensor_ids:
            self._input_sensor_ids = []
            self._input_names = {}
            self._pending_input_sensor_ids = None
            self._update_config_entry_options()
            return await self.async_step_init()

        hass = self.hass
        language = getattr(getattr(hass, "config", None), "language", None)
        if self._input_name_language != language:
            self._input_name_templates = None
            self._input_name_language = language

        if self._input_name_templates is None:
            if hass is None:
                self._input_name_templates = (
                    "Alarm input {number}",
                    "Name of alarm input",
                )
            else:
                self._input_name_templates = await _async_input_name_templates(hass)

        default_template, title_template = self._input_name_templates

        errors: dict[str, str] = {}
        collected: dict[str, str] = {}
        field_labels: dict[int, str] = {}
        defaults: dict[int, str] = {}

        for sensor in sensor_ids:
            label = _format_with_number(title_template, sensor)
            if label == title_template:
                label = f"{label} {sensor}"
            field_labels[sensor] = label
            stored_name = self._input_names.get(str(sensor))
            if stored_name:
                defaults[sensor] = stored_name
                continue
            fallback = _format_with_number(default_template, sensor)
            if fallback == default_template:
                fallback = f"Alarm input {sensor}"
            defaults[sensor] = fallback

        if user_input is not None:
            for sensor in sensor_ids:
                field = field_labels[sensor]
                raw_value = (user_input.get(field) or "").strip()
                if not raw_value:
                    errors[field] = "required"
                else:
                    collected[str(sensor)] = raw_value

            if not errors:
                self._input_sensor_ids = sensor_ids
                self._input_names = collected
                self._pending_input_sensor_ids = None
                self._update_config_entry_options()
                return await self.async_step_init()

        schema_dict: dict[Any, Any] = {}
        for sensor in sensor_ids:
            field = field_labels[sensor]
            schema_dict[vol.Required(field, default=defaults[sensor])] = str

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="input_names",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(sensor_ids))},
        )

    async def async_step_outputs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure which outputs should be exposed as switches."""

        if self._output_switch_ids:
            default_outputs = list(self._output_switch_ids)
        elif CONF_OUTPUT_SWITCHES in self._config_entry.data:
            default_outputs = normalize_input_sensor_config(
                self._config_entry.data.get(CONF_OUTPUT_SWITCHES),
                max_input=INOUT_MAX_COUNT,
            )
        else:
            default_outputs = []

        default_count = len(default_outputs)
        default_value = format_input_sensor_list(default_outputs)

        errors: dict[str, str] = {}

        if user_input is not None:
            count = user_input.get("count", default_count)
            raw_selection = user_input.get(CONF_OUTPUT_SWITCHES, "")

            if count == 0:
                if raw_selection and raw_selection.strip():
                    errors[CONF_OUTPUT_SWITCHES] = "invalid_output"
                else:
                    self._output_switch_ids = []
                    self._output_names = {}
                    self._pending_output_switch_ids = None
                    self._update_config_entry_options()
                    return await self.async_step_init()
            else:
                try:
                    outputs = parse_input_sensor_selection(
                        raw_selection, max_input=INOUT_MAX_COUNT
                    )
                except ValueError:
                    errors[CONF_OUTPUT_SWITCHES] = "invalid_output"
                    outputs = default_outputs
                else:
                    if len(outputs) != count:
                        errors["count"] = "output_count_mismatch"

                if not errors:
                    self._pending_output_switch_ids = outputs
                    self._retain_output_names(outputs)
                    return await self.async_step_output_names()

            schema = vol.Schema(
                {
                    vol.Required("count", default=count): vol.All(
                        int, vol.Range(min=0, max=INOUT_MAX_COUNT)
                    ),
                    vol.Optional(
                        CONF_OUTPUT_SWITCHES,
                        default=raw_selection,
                    ): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("count", default=default_count): vol.All(
                        int, vol.Range(min=0, max=INOUT_MAX_COUNT)
                    ),
                    vol.Optional(CONF_OUTPUT_SWITCHES, default=default_value): str,
                }
            )

        return self.async_show_form(
            step_id="outputs",
            data_schema=schema,
            errors=errors,
            description_placeholders={"max_output": str(INOUT_MAX_COUNT)},
        )

    async def async_step_output_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Assign names to each configured output switch."""

        switch_ids = self._pending_output_switch_ids or self._output_switch_ids
        if not switch_ids:
            self._output_switch_ids = []
            self._output_names = {}
            self._pending_output_switch_ids = None
            self._update_config_entry_options()
            return await self.async_step_init()

        hass = self.hass
        language = getattr(getattr(hass, "config", None), "language", None)
        if self._output_name_language != language:
            self._output_name_templates = None
            self._output_name_language = language

        if self._output_name_templates is None:
            if hass is None:
                self._output_name_templates = (
                    "Output {number}",
                    "Name of output",
                )
            else:
                self._output_name_templates = await _async_output_name_templates(hass)

        default_template, title_template = self._output_name_templates

        errors: dict[str, str] = {}
        collected: dict[str, str] = {}
        field_labels: dict[int, str] = {}
        defaults: dict[int, str] = {}

        for switch in switch_ids:
            label = _format_with_number(title_template, switch)
            if label == title_template:
                label = f"{label} {switch}"
            field_labels[switch] = label
            stored_name = self._output_names.get(str(switch))
            if stored_name:
                defaults[switch] = stored_name
                continue
            fallback = _format_with_number(default_template, switch)
            if fallback == default_template:
                fallback = f"Output {switch}"
            defaults[switch] = fallback

        if user_input is not None:
            for switch in switch_ids:
                field = field_labels[switch]
                raw_value = (user_input.get(field) or "").strip()
                if not raw_value:
                    errors[field] = "required"
                else:
                    collected[str(switch)] = raw_value

            if not errors:
                self._output_switch_ids = switch_ids
                self._output_names = collected
                self._pending_output_switch_ids = None
                self._update_config_entry_options()
                return await self.async_step_init()

        schema_dict: dict[Any, Any] = {}
        for switch in switch_ids:
            field = field_labels[switch]
            schema_dict[vol.Required(field, default=defaults[switch])] = str

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="output_names",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(switch_ids))},
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
        self._panel_index = len(self._panels) - 1
        return await self.async_step_panel_edit()

    def _panel_form_defaults(
        self, index: int, user_input: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Return default values for the single panel editor."""

        panel = self._panels[index]
        defaults: dict[str, Any] = {}

        if user_input is not None:
            defaults["name"] = user_input.get("name", panel.get("name") or "")
            defaults["entity_id_suffix"] = user_input.get(
                "entity_id_suffix", panel.get("entity_id_suffix", "")
            )
            defaults["remove"] = bool(user_input.get("remove", False))
            for mode in MODES:
                defaults[mode] = user_input.get(
                    mode, _format_sector_list(panel.get("modes", {}).get(mode))
                )
        else:
            defaults["name"] = panel.get("name", f"Panel {index + 1}")
            defaults["entity_id_suffix"] = panel.get("entity_id_suffix", "")
            defaults["remove"] = False
            for mode in MODES:
                defaults[mode] = _format_sector_list(panel.get("modes", {}).get(mode))

        return defaults

    def _update_config_entry_options(self) -> None:
        """Persist the current panel and user code configuration."""

        options = panels_to_options(self._panels, max_sector=self._sector_limit)
        options[OPTION_USER_CODES] = list(self._user_codes)
        options[CONF_INPUT_SENSORS] = list(self._input_sensor_ids)
        options[OPTION_INPUT_NAMES] = {
            key: value for key, value in self._input_names.items() if key and value
        }
        options[CONF_OUTPUT_SWITCHES] = list(self._output_switch_ids)
        options[OPTION_OUTPUT_NAMES] = {
            key: value for key, value in self._output_names.items() if key and value
        }
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options=options,
        )

    def _retain_input_names(self, sensor_ids: list[int]) -> None:
        """Preserve configured names for the provided sensor identifiers."""

        existing: dict[str, str] = {}
        for sensor in sensor_ids:
            key = str(sensor)
            if key in self._input_names:
                existing[key] = self._input_names[key]
        self._input_names = existing

    def _retain_output_names(self, switch_ids: list[int]) -> None:
        """Preserve configured names for the provided output identifiers."""

        existing: dict[str, str] = {}
        for switch in switch_ids:
            key = str(switch)
            if key in self._output_names:
                existing[key] = self._output_names[key]
        self._output_names = existing

    async def async_step_panels(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow the user to choose which panel to edit."""

        if not self._panels:
            return self.async_show_form(
                step_id="panels",
                data_schema=vol.Schema({}),
                errors={"base": "no_panels"},
                description_placeholders={
                    "max_sector": str(self._sector_limit),
                },
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            selection = user_input.get("panel")
            try:
                index = int(selection)
            except (TypeError, ValueError):
                errors["panel"] = "invalid_panel"
            else:
                if 0 <= index < len(self._panels):
                    self._panel_index = index
                    return await self.async_step_panel_edit()
                errors["panel"] = "invalid_panel"

        options = [
            selector.SelectOptionDict(
                value=str(index),
                label=panel.get("name") or f"Panel {index + 1}",
            )
            for index, panel in enumerate(self._panels)
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "panel",
                    default=(
                        str(self._panel_index) if self._panel_index is not None else "0"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="panels",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "max_sector": str(self._sector_limit),
            },
        )

    async def async_step_panel_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Display the editor for the selected panel."""

        if self._panel_index is None or self._panel_index >= len(self._panels):
            self._panel_index = None
            return await self.async_step_panels()

        index = self._panel_index
        panel = self._panels[index]
        defaults = self._panel_form_defaults(index, user_input)
        schema_dict: dict[Any, Any] = {
            vol.Required("name", default=defaults["name"]): str,
            vol.Optional("entity_id_suffix", default=defaults["entity_id_suffix"]): str,
        }
        for mode in MODES:
            schema_dict[vol.Optional(mode, default=defaults[mode])] = str
        schema_dict[vol.Optional("remove", default=defaults["remove"])] = bool
        schema = vol.Schema(schema_dict)

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("remove"):
                self._panels.pop(index)
                self._panel_index = None
                self._update_config_entry_options()
                return await self.async_step_init()

            name_input = (user_input.get("name") or "").strip()
            if not name_input:
                errors["name"] = "required"
            name_value = name_input or panel.get("name", f"Panel {index + 1}")

            slug_input = (user_input.get("entity_id_suffix") or "").strip()
            slug_candidate = slugify(slug_input) if slug_input else slugify(name_value)
            if not slug_candidate:
                errors["entity_id_suffix"] = "invalid_slug"
                slug_candidate = (
                    slugify(panel.get("entity_id_suffix") or name_value)
                    or f"panel_{index + 1}"
                )

            modes: dict[str, list[int]] = {}
            for mode in MODES:
                try:
                    sectors = _parse_sector_input(
                        user_input.get(mode, ""), max_sector=self._sector_limit
                    )
                except vol.Invalid:
                    errors[mode] = "invalid_sector"
                    sectors = panel.get("modes", {}).get(mode, [])
                if sectors:
                    modes[mode] = sectors

            slug_value = slug_candidate
            if not errors:
                for other_index, other in enumerate(self._panels):
                    if other_index == index:
                        continue
                    other_slug = slugify(
                        other.get("entity_id_suffix") or other.get("name") or ""
                    )
                    if not other_slug:
                        other_slug = f"panel_{other_index + 1}"
                    if other_slug == slug_value:
                        errors["entity_id_suffix"] = "duplicate_slug"
                        break

            if not errors:
                self._panels[index] = {
                    "name": name_value,
                    "entity_id_suffix": slug_value,
                    "modes": modes,
                }
                self._panel_index = None
                self._update_config_entry_options()
                return await self.async_step_init()

        return self.async_show_form(
            step_id="panel_edit",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "panel_name": panel.get("name", f"Panel {index + 1}"),
                "max_sector": str(self._sector_limit),
            },
        )

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
                self._update_config_entry_options()
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    "codes",
                    default=_format_user_codes(self._user_codes),
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            }
        )

        return self.async_show_form(
            step_id="user_codes",
            data_schema=schema,
            errors=errors,
        )
