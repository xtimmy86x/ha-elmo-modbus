"""Service helpers for the Elmo Modbus integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, INOUT_MAX_COUNT, INPUT_EXCLUDE_START

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from homeassistant.core import ServiceCall
else:  # pragma: no cover - type alias for stubs
    ServiceCall = Any

SERVICE_EXCLUDE_INPUTS = "exclude_inputs"
SERVICE_INCLUDE_INPUTS = "include_inputs"

ATTR_INPUT_ENTITIES = "input_entities"
ATTR_EXCLUDED = "excluded"


def _build_service_schema() -> Any:
    """Return a schema or callable used to validate service data."""

    if hasattr(vol, "Optional") and hasattr(vol, "Schema"):
        return vol.Schema(
            {
                vol.Optional(ATTR_INPUT_ENTITIES, default=[]): cv.entity_ids,
            }
        )

    def _fallback_schema(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise vol.Invalid("invalid service data")

        def _coerce_entities(value: Any) -> list[str]:
            if value in (None, "", []):
                return []
            try:
                return cv.entity_ids(value)
            except Exception as exc:  # pragma: no cover - defensive
                raise vol.Invalid("invalid entity id") from exc

        parsed_data = {
            ATTR_INPUT_ENTITIES: _coerce_entities(data.get(ATTR_INPUT_ENTITIES)),
        }
        return parsed_data

    return _fallback_schema


_SERVICE_BASE_SCHEMA = _build_service_schema()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register Elmo Modbus services if they are not already registered."""

    if hass.services.has_service(DOMAIN, SERVICE_EXCLUDE_INPUTS):
        return

    async def _async_handle_exclude_inputs(call: ServiceCall) -> None:
        await _async_apply_input_exclusion(hass, dict(call.data), excluded=True)

    async def _async_handle_include_inputs(call: ServiceCall) -> None:
        await _async_apply_input_exclusion(hass, dict(call.data), excluded=False)

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXCLUDE_INPUTS,
        _async_handle_exclude_inputs,
        schema=_SERVICE_BASE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INCLUDE_INPUTS,
        _async_handle_include_inputs,
        schema=_SERVICE_BASE_SCHEMA,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the Elmo Modbus services when no longer needed."""

    if not hass.services.has_service(DOMAIN, SERVICE_EXCLUDE_INPUTS):
        return

    hass.services.async_remove(DOMAIN, SERVICE_EXCLUDE_INPUTS)
    hass.services.async_remove(DOMAIN, SERVICE_INCLUDE_INPUTS)


def _group_input_entities_by_entry(
    hass: HomeAssistant, entity_ids: Iterable[str]
) -> dict[str, set[int]]:
    """Return input numbers grouped by the config entry they belong to."""

    registry = er.async_get(hass)
    grouped: dict[str, set[int]] = {}

    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if not entry or entry.platform != DOMAIN or not entry.unique_id:
            continue
        config_entry_id = entry.config_entry_id
        if not config_entry_id:
            continue

        _, _, key = entry.unique_id.partition(":binary:")
        if not key.startswith("alarm_input_"):
            continue
        try:
            index = int(key.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if index < 1 or index > INOUT_MAX_COUNT:
            continue

        grouped.setdefault(config_entry_id, set()).add(index)

    return grouped


async def _async_handle_set_input_exclusion(
    hass: HomeAssistant, call: Any
) -> None:
    """Backward compatible wrapper used by the unit tests."""

    data = dict(getattr(call, "data", {}))
    excluded = bool(data.get(ATTR_EXCLUDED))
    await _async_apply_input_exclusion(hass, data, excluded=excluded)


async def _async_apply_input_exclusion(
    hass: HomeAssistant, data: dict[str, Any], *, excluded: bool
) -> None:
    """Process a service call to include or exclude alarm inputs."""

    parsed = _SERVICE_BASE_SCHEMA(data)
    input_entity_ids = parsed.get(ATTR_INPUT_ENTITIES, [])
    entity_mapping = _group_input_entities_by_entry(hass, input_entity_ids)
    target_entries: dict[str, set[int]] = {
        entry_id: set(numbers) for entry_id, numbers in entity_mapping.items()
    }
    if not target_entries:
        _LOGGER.warning("No valid alarm inputs specified for service call")
        return

    value = not excluded
    for entry_id, numbers in target_entries.items():
        if not numbers:
            continue
        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if not entry_data:
            continue
        inventory = entry_data.get("inventory")
        coordinator = entry_data.get("coordinator")
        if inventory is None or coordinator is None:
            continue

        for index in sorted(numbers):
            address = INPUT_EXCLUDE_START + index - 1
            await hass.async_add_executor_job(inventory.write_coil, address, value)

        await coordinator.async_request_refresh()