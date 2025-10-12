"""Service handlers for the Elmo Modbus integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, TYPE_CHECKING

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall
else:  # pragma: no cover - runtime fallback for test stubs
    try:
        from homeassistant.core import ServiceCall
    except ImportError:
        try:
            from homeassistant.helpers.typing import ServiceCall  # type: ignore[attr-defined]
        except (ImportError, AttributeError):

            class ServiceCall(Protocol):  # type: ignore[misc, assignment]
                """Fallback ServiceCall protocol used in tests."""

                data: dict[str, Any]

from homeassistant.exceptions import HomeAssistantError

try:  # pragma: no cover - optional dependency for unit tests
    from homeassistant.helpers import device_registry as dr
except ImportError:  # pragma: no cover - provided by Home Assistant at runtime
    dr = None  # type: ignore[assignment]

try:  # pragma: no cover - provided by Home Assistant at runtime
    from homeassistant.helpers import config_validation as cv
except ImportError:  # pragma: no cover - used in unit test environment
    cv = None  # type: ignore[assignment]

try:  # pragma: no cover - provided by Home Assistant at runtime
    from homeassistant.helpers import entity_registry as er
except ImportError:  # pragma: no cover - used in unit test environment
    er = None  # type: ignore[assignment]

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
ATTR_INPUT_ENTITIES = "input_entities"
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

def _normalize_entity_ids(value: Any) -> list[str]:
    """Validate and normalise a collection of entity identifiers."""

    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        candidates = list(value)
    else:
        raise vol.Invalid("invalid_entity_id")

    entity_ids: list[str] = []
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if not text or "." not in text:
            raise vol.Invalid("invalid_entity_id")
        entity_ids.append(text)

    if not entity_ids:
        raise vol.Invalid("invalid_entity_id")

    return entity_ids


def _ensure_inputs_specified(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure that either numeric inputs or input entities were provided."""

    inputs = data.get(ATTR_INPUTS)
    if inputs:
        return data

    entities = data.get(ATTR_INPUT_ENTITIES)
    if entities:
        return data

    target_entities = data.get("entity_id")
    if target_entities:
        for entity_id in target_entities:
            if str(entity_id).split(".")[0] == "binary_sensor":
                return data

    raise vol.Invalid(f"missing required key: {ATTR_INPUTS}")

if hasattr(vol, "Optional"):
    _entity_ids_validator = (
        vol.All(cv.entity_ids, vol.Length(min=1)) if cv else vol.All(_normalize_entity_ids, vol.Length(min=1))
    )

    _SERVICE_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Optional(ATTR_INPUTS): _validate_inputs,
                vol.Optional(ATTR_INPUT_ENTITIES): _entity_ids_validator,
                vol.Optional(ATTR_EXCLUDED, default=True): _coerce_bool,
                vol.Optional(ATTR_CONFIG_ENTRY_ID, default=None): _coerce_optional_str,
                vol.Optional(ATTR_DEVICE_ID, default=None): _coerce_optional_str,
                vol.Optional("entity_id"): _entity_ids_validator,
            },
            extra=vol.ALLOW_EXTRA,
        ),
        _ensure_inputs_specified,
    )

else:  # pragma: no cover - executed only by unit test stubs

    def _SERVICE_SCHEMA(data: dict[str, Any]) -> dict[str, Any]:
        """Fallback schema validator when voluptuous optional is unavailable."""

        validated: dict[str, Any] = {}
        inputs: list[int] | None = None
        if ATTR_INPUTS in data and data[ATTR_INPUTS] not in (None, ""):
            inputs = _validate_inputs(data[ATTR_INPUTS])
            validated[ATTR_INPUTS] = inputs

        if ATTR_INPUT_ENTITIES in data and data[ATTR_INPUT_ENTITIES] not in (None, ""):
            entities = _normalize_entity_ids(data[ATTR_INPUT_ENTITIES])
            validated[ATTR_INPUT_ENTITIES] = entities
        else:
            entities = None

        target_entities: list[str] | None = None
        if "entity_id" in data and data["entity_id"] not in (None, ""):
            target_entities = _normalize_entity_ids(data["entity_id"])
            validated["entity_id"] = target_entities

        if not inputs and not entities:
            binary_targets = [
                entity_id
                for entity_id in target_entities or []
                if entity_id.split(".")[0] == "binary_sensor"
            ]
            if not binary_targets:
                raise vol.Invalid(f"missing required key: {ATTR_INPUTS}")

        validated[ATTR_EXCLUDED] = _coerce_bool(data.get(ATTR_EXCLUDED, True))
        validated[ATTR_CONFIG_ENTRY_ID] = _coerce_optional_str(
            data.get(ATTR_CONFIG_ENTRY_ID)
        )
        validated[ATTR_DEVICE_ID] = _coerce_optional_str(data.get(ATTR_DEVICE_ID))

        for key, value in data.items():
            validated.setdefault(key, value)

        return validated


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
    hass: HomeAssistant,
    *,
    config_entry_id: str | None,
    device_id: str | None,
    entity_ids: Iterable[str] | None = None,
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
        if dr is None:
            raise HomeAssistantError("Device registry is not available.")
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

    if entity_ids:
        if er is None:
            raise HomeAssistantError("Entity registry is not available.")
        registry = er.async_get(hass)
        for entity_id in entity_ids:
            entry = registry.async_get(entity_id)
            if entry is None:
                raise HomeAssistantError(
                    f"Entity {entity_id} not found in entity registry."
                )
            platform = getattr(entry, "platform", None)
            config_id = getattr(entry, "config_entry_id", None)
            if platform != DOMAIN or config_id not in entries:
                raise HomeAssistantError(
                    "Entity does not belong to an Elmo Modbus config entry."
                )
            result.add(config_id)

    if result:
        return sorted(result)

    if len(entries) == 1:
        return [next(iter(entries))]

    raise HomeAssistantError(
        "Multiple Elmo Modbus entries configured; specify config_entry_id or device_id."
    )

def _group_input_entities_by_entry(
    hass: HomeAssistant, entity_ids: Iterable[str]
) -> dict[str, set[int]]:
    """Return mapping of config entry IDs to input indices from entity ids."""

    identifiers = list(dict.fromkeys(entity_ids))
    if not identifiers:
        return {}

    if er is None:
        raise HomeAssistantError("Entity registry is not available.")

    entries = _active_entries(hass)
    registry = er.async_get(hass)
    mapping: dict[str, set[int]] = {}

    for entity_id in identifiers:
        entry = registry.async_get(entity_id)
        if entry is None:
            raise HomeAssistantError(
                f"Entity {entity_id} not found in entity registry."
            )

        platform = getattr(entry, "platform", None)
        if platform != DOMAIN:
            raise HomeAssistantError(
                "Entity does not belong to the Elmo Modbus integration."
            )

        domain = entity_id.split(".")[0]
        if domain != "binary_sensor":
            raise HomeAssistantError("Entity is not an Elmo Modbus alarm input.")

        unique_id = str(getattr(entry, "unique_id", "") or "")
        prefix, marker, suffix = unique_id.partition(":binary:alarm_input_")
        if marker != ":binary:alarm_input_":
            raise HomeAssistantError("Entity is not an Elmo Modbus alarm input.")

        try:
            input_index = int(suffix)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Entity is not an Elmo Modbus alarm input.") from err

        if input_index < 1 or input_index > INOUT_MAX_COUNT:
            raise HomeAssistantError("Entity input index is out of range.")

        config_entry_id = getattr(entry, "config_entry_id", None)
        if config_entry_id is None or config_entry_id not in entries:
            raise HomeAssistantError(
                "Entity does not belong to a loaded Elmo Modbus config entry."
            )

        mapping.setdefault(config_entry_id, set()).add(input_index)

    return mapping

async def _async_handle_set_input_exclusion(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Handle the set_input_exclusion service call."""

    inputs: list[int] = call.data.get(ATTR_INPUTS) or []
    excluded: bool = call.data[ATTR_EXCLUDED]
    config_entry_id: str | None = call.data.get(ATTR_CONFIG_ENTRY_ID)
    device_id: str | None = call.data.get(ATTR_DEVICE_ID)

    raw_input_entities = call.data.get(ATTR_INPUT_ENTITIES)
    if isinstance(raw_input_entities, str):
        input_entities = [raw_input_entities]
    elif isinstance(raw_input_entities, Iterable):
        input_entities = [str(entity) for entity in raw_input_entities]
    else:
        input_entities = []

    raw_target_entity_ids = call.data.get("entity_id")
    if isinstance(raw_target_entity_ids, str):
        target_entity_ids = [raw_target_entity_ids]
    elif isinstance(raw_target_entity_ids, Iterable):
        target_entity_ids = [str(entity) for entity in raw_target_entity_ids]
    else:
        target_entity_ids = []

    combined_entity_ids = list(dict.fromkeys([*target_entity_ids, *input_entities]))

    entry_ids = _resolve_entry_ids(
        hass,
        config_entry_id=config_entry_id,
        device_id=device_id,
        entity_ids=combined_entity_ids or None,
    )

    additional_input_entities = [
        entity_id for entity_id in target_entity_ids if entity_id.startswith("binary_sensor.")
    ]
    entity_inputs = _group_input_entities_by_entry(
        hass, [*input_entities, *additional_input_entities]
    )

    desired_value = not excluded  # False => exclude, True => activate

    for entry_id in entry_ids:
        entry_data = hass.data[DOMAIN][entry_id]
        inventory: ElmoModbusInventory = entry_data["inventory"]
        coordinator: ElmoModbusCoordinator = entry_data["coordinator"]

        selected_inputs = set(inputs)
        selected_inputs.update(entity_inputs.get(entry_id, set()))
        if not selected_inputs:
            raise HomeAssistantError(
                "No inputs were provided for the selected config entry."
            )

        addresses = [
            INPUT_SENSOR_EXCLUDED_START + index - 1 for index in sorted(selected_inputs)
        ]

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
