"""Service handlers for the Elmo Modbus integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
import voluptuous as vol

import logging
_LOGGER = logging.getLogger(__name__)   # Logger for this module

from pymodbus.exceptions import ConnectionException

from .const import DOMAIN, INOUT_MAX_COUNT, INPUT_SENSOR_EXCLUDED_START
from .coordinator import ElmoModbusCoordinator, ElmoModbusInventory
from .input_selectors import parse_input_sensor_selection

SERVICE_SET_INPUT_EXCLUSION = "set_input_exclusion"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_EXCLUDED = "excluded"
ATTR_INPUTS = "inputs"
SERVICES_KEY = "_services"
_REGISTERED = "registered"


def _coerce_bool(value: Any) -> bool:
    """Validate and coerce a truthy value into a boolean."""

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False

    raise vol.Invalid("invalid_boolean")


def _validate_inputs(value: Any) -> list[int]:
    """Validate service inputs and return a sorted list of unique ids."""

    if isinstance(value, str):
        try:
            result = parse_input_sensor_selection(value, max_input=INOUT_MAX_COUNT)
        except ValueError as err:
            raise vol.Invalid("invalid_inputs") from err
        return result

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        items = list(value)
    else:
        items = [value]

    numbers: set[int] = set()
    for item in items:
        try:
            number = int(item)
        except (TypeError, ValueError) as err:
            raise vol.Invalid("invalid_inputs") from err
        if number < 1 or number > INOUT_MAX_COUNT:
            raise vol.Invalid("invalid_inputs")
        numbers.add(number)

    if not numbers:
        raise vol.Invalid("invalid_inputs")

    return sorted(numbers)


def _coerce_optional_str(value: Any) -> str | None:
    """Return a stripped string or None when no value is provided."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    return text


_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_INPUTS): _validate_inputs,
        vol.Optional(ATTR_EXCLUDED, default=True): _coerce_bool,
        vol.Optional(ATTR_CONFIG_ENTRY_ID, default=None): _coerce_optional_str,
        vol.Optional(ATTR_DEVICE_ID, default=None): _coerce_optional_str,
    }
)


def _active_entries(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return the mapping of active config entries for the integration."""

    domain_data: dict[str, Any] = hass.data.setdefault(DOMAIN, {})
    return {
        key: value
        for key, value in domain_data.items()
        if isinstance(value, dict)
        and "inventory" in value
        and "coordinator" in value
    }


def _resolve_entry_ids(
    hass: HomeAssistant, *, config_entry_id: str | None, device_id: str | None
) -> list[str]:
    """Determine which config entries should receive the service call."""

    entries = _active_entries(hass)
    if not entries:
        raise HomeAssistantError("No Elmo Modbus config entries are loaded.")

    result: set[str] = set()

    if config_entry_id:
        if config_entry_id not in entries:
            raise HomeAssistantError(
                f"Config entry {config_entry_id} is not an Elmo Modbus entry."
            )
        result.add(config_entry_id)

    if device_id:
        registry = dr.async_get(hass)
        device = registry.async_get(device_id)
        if device is None:
            raise HomeAssistantError(f"Device {device_id} not found in device registry.")
        matched = False
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier in entries:
                matched = True
                result.add(identifier)
        if not matched:
            raise HomeAssistantError(
                "Device does not belong to an Elmo Modbus config entry."
            )

    if result:
        return sorted(result)

    if len(entries) == 1:
        return [next(iter(entries))]

    raise HomeAssistantError(
        "Multiple Elmo Modbus entries configured; specify config_entry_id or device_id."
    )


async def _async_handle_set_input_exclusion(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Handle the set_input_exclusion service call."""

    inputs: list[int] = call.data[ATTR_INPUTS]
    excluded: bool = call.data[ATTR_EXCLUDED]
    config_entry_id: str | None = call.data.get(ATTR_CONFIG_ENTRY_ID)
    device_id: str | None = call.data.get(ATTR_DEVICE_ID)

    entry_ids = _resolve_entry_ids(
        hass, config_entry_id=config_entry_id, device_id=device_id
    )

    addresses = [INPUT_SENSOR_EXCLUDED_START + index - 1 for index in inputs]
    desired_value = not excluded  # False => exclude, True => activate

    for entry_id in entry_ids:
        entry_data = hass.data[DOMAIN][entry_id]
        inventory: ElmoModbusInventory = entry_data["inventory"]
        coordinator: ElmoModbusCoordinator = entry_data["coordinator"]

        def _write() -> None:
            for address in addresses:
                inventory.write_coil(address, desired_value)

        try:
            await hass.async_add_executor_job(_write)
        except ConnectionException as err:
            raise HomeAssistantError(
                "Failed to update input exclusion state via Modbus."
            ) from err

        await coordinator.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services if not already registered."""

    domain_data: dict[str, Any] = hass.data.setdefault(DOMAIN, {})
    services_state: dict[str, Any] = domain_data.setdefault(SERVICES_KEY, {})
    if services_state.get(_REGISTERED):
        return
    async def _async_service_handler(call: ServiceCall) -> None:
        await _async_handle_set_input_exclusion(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INPUT_EXCLUSION,
        _async_service_handler,
        schema=_SERVICE_SCHEMA,
    )
    services_state[_REGISTERED] = True

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload registered services when no entries remain."""

    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})
    services_state: dict[str, Any] | None = domain_data.get(SERVICES_KEY)

    if not services_state or not services_state.get(_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_SET_INPUT_EXCLUSION)
    services_state.pop(_REGISTERED, None)
    if not services_state:
        domain_data.pop(SERVICES_KEY, None)
