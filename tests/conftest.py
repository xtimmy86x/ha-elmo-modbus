"""Test configuration and Home Assistant stubs."""

from __future__ import annotations

import pathlib
import sys
import types
from typing import Any, Callable, Generic, TypeVar

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _slugify(value: Any) -> str:
    """Simplified slugify helper compatible with Home Assistant."""

    text = str(value or "").strip().lower()
    return "".join(char if char.isalnum() else "_" for char in text).strip("_")


def pytest_configure() -> None:
    """Install stub Home Assistant modules for unit tests."""

    if "homeassistant" in sys.modules:
        return

    ha_module = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_module

    # homeassistant.util
    util_module = types.ModuleType("homeassistant.util")
    util_module.slugify = _slugify  # type: ignore[attr-defined]
    sys.modules["homeassistant.util"] = util_module
    ha_module.util = util_module  # type: ignore[attr-defined]

    # homeassistant.core
    core_module = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - helper for typing in tests
        """Minimal HomeAssistant placeholder."""

        class config:  # type: ignore[valid-type]
            language = "en"

    def callback(func: Callable[..., Any]) -> Callable[..., Any]:
        """Return the wrapped callback unchanged."""

        return func

    core_module.HomeAssistant = HomeAssistant  # type: ignore[attr-defined]
    core_module.callback = callback  # type: ignore[attr-defined]
    sys.modules["homeassistant.core"] = core_module
    ha_module.core = core_module  # type: ignore[attr-defined]

    # homeassistant.data_entry_flow
    data_entry_flow_module = types.ModuleType("homeassistant.data_entry_flow")
    data_entry_flow_module.FlowResult = dict  # type: ignore[attr-defined]
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_module
    ha_module.data_entry_flow = data_entry_flow_module  # type: ignore[attr-defined]

    # homeassistant.helpers.selector
    selector_module = types.ModuleType("homeassistant.helpers.selector")

    class SelectOptionDict(dict):  # pragma: no cover - support structure only
        def __init__(self, *, value: str, label: str) -> None:
            super().__init__(value=value, label=label)

    class SelectSelectorConfig:
        def __init__(self, *, options: list[Any], mode: Any) -> None:
            self.options = options
            self.mode = mode

    class SelectSelector:
        def __init__(self, config: SelectSelectorConfig) -> None:
            self.config = config

    class TextSelectorConfig:
        def __init__(self, *, multiline: bool = False) -> None:
            self.multiline = multiline

    class TextSelector:
        def __init__(self, config: TextSelectorConfig) -> None:
            self.config = config

    class _SelectorMode:
        DROPDOWN = "dropdown"

    selector_module.SelectOptionDict = SelectOptionDict  # type: ignore[attr-defined]
    selector_module.SelectSelectorConfig = SelectSelectorConfig  # type: ignore[attr-defined]
    selector_module.SelectSelector = SelectSelector  # type: ignore[attr-defined]
    selector_module.TextSelectorConfig = TextSelectorConfig  # type: ignore[attr-defined]
    selector_module.TextSelector = TextSelector  # type: ignore[attr-defined]
    selector_module.SelectSelectorMode = _SelectorMode  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.selector"] = selector_module
    helpers_module = types.ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []  # type: ignore[attr-defined]
    helpers_module.selector = selector_module  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers"] = helpers_module
    ha_module.helpers = helpers_module  # type: ignore[attr-defined]

    # homeassistant.helpers.config_validation
    config_validation_module = types.ModuleType(
        "homeassistant.helpers.config_validation"
    )

    def config_entry_only_config_schema(domain: str) -> Callable[[Any], Any]:
        """Return a pass-through schema callable for tests."""

        def _schema(value: Any) -> Any:
            return value

        return _schema

    config_validation_module.config_entry_only_config_schema = (
        config_entry_only_config_schema  # type: ignore[attr-defined]
    )
    sys.modules["homeassistant.helpers.config_validation"] = config_validation_module
    helpers_module.config_validation = config_validation_module  # type: ignore[attr-defined]

    # homeassistant.helpers.translation
    translation_module = types.ModuleType("homeassistant.helpers.translation")

    async def async_get_translations(*_: Any, **__: Any) -> dict[str, str]:
        return {}

    translation_module.async_get_translations = async_get_translations  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.translation"] = translation_module
    helpers_module.translation = translation_module  # type: ignore[attr-defined]

    update_coordinator_module = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )

    _T = TypeVar("_T")

    class DataUpdateCoordinator(Generic[_T]):  # pragma: no cover - behaviour mocked
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.hass = args[0] if args else None

        async def async_add_executor_job(self, func: Callable[..., Any], *args: Any) -> Any:
            return func(*args)

    class UpdateFailed(Exception):
        pass

    update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator  # type: ignore[attr-defined]
    update_coordinator_module.UpdateFailed = UpdateFailed  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module
    helpers_module.update_coordinator = update_coordinator_module  # type: ignore[attr-defined]

    typing_module = types.ModuleType("homeassistant.helpers.typing")
    typing_module.ConfigType = dict  # type: ignore[attr-defined]
    typing_module.HomeAssistantType = object  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.typing"] = typing_module
    helpers_module.typing = typing_module  # type: ignore[attr-defined]

    # homeassistant.config_entries
    config_entries_module = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:  # pragma: no cover - placeholder only
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:  # pragma: no cover - stub
            super().__init_subclass__()

    class OptionsFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:  # pragma: no cover - stub
            super().__init_subclass__()

    config_entries_module.ConfigEntry = ConfigEntry  # type: ignore[attr-defined]
    config_entries_module.ConfigFlow = ConfigFlow  # type: ignore[attr-defined]
    config_entries_module.OptionsFlow = OptionsFlow  # type: ignore[attr-defined]
    sys.modules["homeassistant.config_entries"] = config_entries_module
    ha_module.config_entries = config_entries_module  # type: ignore[attr-defined]

    # pymodbus client stubs
    pymodbus_module = types.ModuleType("pymodbus")
    pymodbus_client_module = types.ModuleType("pymodbus.client")

    class ModbusTcpClient:  # pragma: no cover - placeholder only
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.connected = False

        def connect(self) -> bool:
            self.connected = True
            return True

        def close(self) -> None:
            self.connected = False

    pymodbus_client_module.ModbusTcpClient = ModbusTcpClient  # type: ignore[attr-defined]
    sys.modules["pymodbus.client"] = pymodbus_client_module

    pymodbus_exceptions_module = types.ModuleType("pymodbus.exceptions")

    class ConnectionException(Exception):
        pass

    pymodbus_exceptions_module.ConnectionException = ConnectionException  # type: ignore[attr-defined]
    sys.modules["pymodbus.exceptions"] = pymodbus_exceptions_module

    pymodbus_module.client = pymodbus_client_module  # type: ignore[attr-defined]
    pymodbus_module.exceptions = pymodbus_exceptions_module  # type: ignore[attr-defined]
    sys.modules["pymodbus"] = pymodbus_module

    # voluptuous
    voluptuous_module = types.ModuleType("voluptuous")

    class Invalid(Exception):
        """Exception raised when validation fails."""

    class Required:
        def __init__(self, key: str, default: Any | types.EllipsisType = ...):
            self.key = key
            self.default = default

    class Range:
        def __init__(self, *, min: int | None = None, max: int | None = None) -> None:
            self.min = min
            self.max = max

        def __call__(self, value: int) -> int:
            if not isinstance(value, int):
                raise Invalid("not an integer")
            if self.min is not None and value < self.min:
                raise Invalid("value too small")
            if self.max is not None and value > self.max:
                raise Invalid("value too large")
            return value

    class All:
        def __init__(self, *validators: Callable[[Any], Any]) -> None:
            self.validators = validators

        def __call__(self, value: Any) -> Any:
            result = value
            for validator in self.validators:
                result = _apply_validator(validator, result)
            return result

    def _apply_validator(validator: Callable[[Any], Any] | type, value: Any) -> Any:
        if isinstance(validator, All):
            return validator(value)
        if isinstance(validator, Range):
            return validator(value)
        return validator(value)  # type: ignore[call-arg]

    class Schema:
        def __init__(self, schema: dict[Any, Any]) -> None:
            self._schema = schema

        def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, validator in self._schema.items():
                default = ...
                if isinstance(key, Required):
                    name = key.key
                    default = key.default
                else:
                    name = key
                if name in data:
                    value = data[name]
                elif default is not ...:
                    value = default
                else:
                    raise Invalid(f"missing required key: {name}")
                result[name] = _apply_validator(validator, value)
            # Preserve extra values untouched
            for name, value in data.items():
                result.setdefault(name, value)
            return result

    voluptuous_module.Invalid = Invalid  # type: ignore[attr-defined]
    voluptuous_module.Required = Required  # type: ignore[attr-defined]
    voluptuous_module.All = All  # type: ignore[attr-defined]
    voluptuous_module.Range = Range  # type: ignore[attr-defined]
    voluptuous_module.Schema = Schema  # type: ignore[attr-defined]
    sys.modules["voluptuous"] = voluptuous_module
