"""Service helpers for the Elmo Modbus integration."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

import voluptuous as vol

try:
    from homeassistant.const import ATTR_ENTITY_ID
except ModuleNotFoundError:  # pragma: no cover - test fallback
    ATTR_ENTITY_ID = "entity_id"  # type: ignore[assignment]
from homeassistant.core import HomeAssistant

try:
    from homeassistant.core import ServiceCall
except ImportError:  # pragma: no cover - test fallback
    class ServiceCall:  # type: ignore[too-few-public-methods]
        """Simple stand-in for Home Assistant ServiceCall."""

        def __init__(self, data: dict[str, object] | None = None) -> None:
            self.data = data or {}

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from pymodbus.exceptions import ConnectionException

from .const import (
    DOMAIN,
    INOUT_MAX_COUNT,
    INPUT_SENSOR_EXCLUDED_START,
)

ATTR_INPUTS = "inputs"
ATTR_INPUT_ENTITIES = "input_entities"
ATTR_EXCLUDED = "excluded"

SERVICE_EXCLUDE_INPUTS = "exclude_inputs"
SERVICE_INCLUDE_INPUTS = "include_inputs"

DATA_SERVICES = "services"


def _ensure_sequence(value: object) -> list[object]:
    """Normalise the provided value into a list."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _coerce_entity_ids(value: object) -> list[str]:
    """Validate and normalise entity IDs using Home Assistant helpers."""

    try:
        return cv.entity_ids(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid("invalid_entity_id") from err


def _coerce_input_numbers(value: object) -> list[int]:
    """Validate and normalise raw alarm input numbers."""

    numbers: list[int] = []
    for item in _ensure_sequence(value):
        try:
            number = int(item)  # type: ignore[arg-type]
        except (TypeError, ValueError) as err:
            raise vol.Invalid("invalid_input_number") from err
        if number < 1 or number > INOUT_MAX_COUNT:
            raise vol.Invalid("invalid_input_number")
        if number not in numbers:
            numbers.append(number)
    return numbers

def _ensure_inputs_present(data: MappingProxyType[str, object] | dict[str, object]) -> dict[str, object]:
    """Validate that at least one input selector has been provided."""

    if isinstance(data, MappingProxyType):
        source = dict(data)
    else:
        source = data

    if source.get(ATTR_INPUT_ENTITIES) or source.get(ATTR_INPUTS):
        return source

    raise vol.Invalid("missing_alarm_inputs")


_SCHEMA_KWARGS: dict[str, object] = {}
_extra = getattr(vol, "PREVENT_EXTRA", None)
if _extra is not None:
    _SCHEMA_KWARGS["extra"] = _extra

if hasattr(vol, "Schema") and hasattr(vol, "Optional"):
    _SERVICE_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Optional(ATTR_INPUT_ENTITIES): _coerce_entity_ids,
                vol.Optional(ATTR_INPUTS): _coerce_input_numbers,
                vol.Optional(ATTR_ENTITY_ID): _coerce_entity_ids,
            },
            **_SCHEMA_KWARGS,
        ),
        _ensure_inputs_present,
    )
else:
    def _SERVICE_SCHEMA(value: dict[str, object]) -> dict[str, object]:
        if not isinstance(value, dict):
            raise vol.Invalid("invalid_service_data")
        allowed = {ATTR_INPUT_ENTITIES, ATTR_INPUTS, ATTR_ENTITY_ID}
        unexpected = set(value) - allowed
        if unexpected:
            raise vol.Invalid("invalid_service_data")

        result: dict[str, object] = {}
        if ATTR_INPUT_ENTITIES in value:
            result[ATTR_INPUT_ENTITIES] = _coerce_entity_ids(
                value[ATTR_INPUT_ENTITIES]
            )
        if ATTR_INPUTS in value:
            result[ATTR_INPUTS] = _coerce_input_numbers(value[ATTR_INPUTS])
        if ATTR_ENTITY_ID in value:
            result[ATTR_ENTITY_ID] = _coerce_entity_ids(value[ATTR_ENTITY_ID])

        return _ensure_inputs_present(result)


def _group_input_entities_by_entry(
    hass: HomeAssistant, entity_ids: Iterable[str] | None
) -> dict[str, set[int]]:
    """Return a mapping of config entry IDs to alarm input numbers."""

    if not entity_ids:
        return {}

    registry = er.async_get(hass)
    mapping: dict[str, set[int]] = {}

    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != DOMAIN:
            continue
        config_entry_id = entry.config_entry_id
        if config_entry_id is None:
            continue
        unique_id = entry.unique_id
        if not unique_id:
            continue
        prefix = f"{config_entry_id}:binary:alarm_input_"
        if not unique_id.startswith(prefix):
            continue
        try:
            index = int(unique_id[len(prefix) :])
        except ValueError:
            continue
        if index < 1 or index > INOUT_MAX_COUNT:
            continue
        mapping.setdefault(config_entry_id, set()).add(index)

    return mapping


def _resolve_target_entries(
    hass: HomeAssistant, entity_ids: Iterable[str] | None
) -> set[str]:
    """Return config entry IDs referenced by the given entity IDs."""

    if not entity_ids:
        return set()

    registry = er.async_get(hass)
    entries: set[str] = set()

    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != DOMAIN:
            continue
        config_entry_id = entry.config_entry_id
        if config_entry_id is None:
            continue
        if config_entry_id not in hass.data.get(DOMAIN, {}):
            continue
        entries.add(config_entry_id)

    return entries


def _apply_input_state(inventory, indexes: Iterable[int], value: bool) -> None:
    """Write the requested coil values for the provided inputs."""

    for index in sorted(set(indexes)):
        address = INPUT_SENSOR_EXCLUDED_START + index - 1
        inventory.write_coil(address, value)


async def _async_handle_set_input_exclusion(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    excluded: bool | None = None,
) -> None:
    """Handle a service call that toggles alarm input exclusion."""

    data = call.data
    if excluded is None:
        excluded = bool(data.get(ATTR_EXCLUDED))

    mapping = _group_input_entities_by_entry(
        hass, data.get(ATTR_INPUT_ENTITIES)
    )
    target_entries = _resolve_target_entries(hass, data.get(ATTR_ENTITY_ID))

    direct_inputs = {int(value) for value in data.get(ATTR_INPUTS, [])}
    if direct_inputs:
        if not target_entries and len(mapping) == 1:
            target_entries = set(mapping)
        if not target_entries:
            raise HomeAssistantError(
                "Specify a target entity when using raw input numbers."
            )
        if len(target_entries) > 1:
            raise HomeAssistantError("Ambiguous target entity for input numbers.")
        entry_id = next(iter(target_entries))
        mapping.setdefault(entry_id, set()).update(direct_inputs)

    if not mapping:
        raise HomeAssistantError("No valid Elmo Modbus input sensors were provided.")

    value = not bool(excluded)

    for entry_id, indexes in mapping.items():
        if not indexes:
            continue
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(entry_id)
        if not entry_data:
            raise HomeAssistantError(
                "The targeted Elmo Modbus config entry is not loaded."
            )

        inventory = entry_data["inventory"]
        coordinator = entry_data["coordinator"]

        try:
            await hass.async_add_executor_job(
                _apply_input_state, inventory, indexes, value
            )
        except ConnectionException as err:
            raise HomeAssistantError(
                f"Failed to write exclusion state to the Modbus device: {err}"
            ) from err

        await coordinator.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Elmo Modbus services if not already available."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    service_data = domain_data.setdefault(DATA_SERVICES, {})
    if service_data.get("registered"):
        return

    async def _handle_exclude(call: ServiceCall) -> None:
        await _async_handle_set_input_exclusion(hass, call, excluded=True)

    async def _handle_include(call: ServiceCall) -> None:
        await _async_handle_set_input_exclusion(hass, call, excluded=False)

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXCLUDE_INPUTS,
        _handle_exclude,
        schema=_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INCLUDE_INPUTS,
        _handle_include,
        schema=_SERVICE_SCHEMA,
    )

    service_data["registered"] = True


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the Elmo Modbus services if no entries remain."""

    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return

    service_data = domain_data.get(DATA_SERVICES)
    if not service_data or not service_data.get("registered"):
        return

    active_entries = [
        key for key in domain_data.keys() if key not in {DATA_SERVICES}
    ]
    if active_entries:
        return

    hass.services.async_remove(DOMAIN, SERVICE_EXCLUDE_INPUTS)
    hass.services.async_remove(DOMAIN, SERVICE_INCLUDE_INPUTS)
    service_data["registered"] = False
    domain_data.pop(DATA_SERVICES, None)


__all__ = [
    "ATTR_INPUTS",
    "ATTR_INPUT_ENTITIES",
    "ATTR_EXCLUDED",
    "SERVICE_EXCLUDE_INPUTS",
    "SERVICE_INCLUDE_INPUTS",
    "async_setup_services",
    "async_unload_services",
    "_group_input_entities_by_entry",
    "_async_handle_set_input_exclusion",
]