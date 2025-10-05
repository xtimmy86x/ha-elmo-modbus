"""Tests for helper utilities in ``config_flow``."""

from __future__ import annotations

import importlib

import pytest
import voluptuous as vol

config_flow = importlib.import_module("custom_components.elmo-modbus.config_flow")


def test_format_with_number_placeholder() -> None:
    """Values should be interpolated into templates when possible."""

    assert config_flow._format_with_number("Sensor {number}", 4) == "Sensor 4"


def test_format_with_number_invalid_placeholder() -> None:
    """Unexpected placeholders should leave the template untouched."""

    template = "Sensor {invalid}"
    assert config_flow._format_with_number(template, 5) == template


def test_format_sector_list_roundtrip() -> None:
    """Formatting sectors should join sorted integers."""

    assert config_flow._format_sector_list([3, 1, 2]) == "3, 1, 2"
    assert config_flow._format_sector_list([]) == ""
    assert config_flow._format_sector_list(None) == ""


def test_parse_sector_input_valid() -> None:
    """Valid sector strings should be normalised and sorted."""

    assert config_flow._parse_sector_input("1, 3, 2; 4", max_sector=8) == [1, 2, 3, 4]
    assert config_flow._parse_sector_input("", max_sector=4) == []


def test_parse_sector_input_invalid_value() -> None:
    """Invalid sector identifiers should raise :class:`vol.Invalid`."""

    with pytest.raises(vol.Invalid):
        config_flow._parse_sector_input("0", max_sector=4)

    with pytest.raises(vol.Invalid):
        config_flow._parse_sector_input("5", max_sector=4)


def test_parse_sector_input_duplicate_entries() -> None:
    """Duplicate sectors should be removed without error."""

    assert config_flow._parse_sector_input("1,1,2,2", max_sector=4) == [1, 2]


def test_format_user_codes() -> None:
    """Stored codes should be joined with new lines."""

    assert config_flow._format_user_codes(["1234", "5678"]) == "1234\n5678"
    assert config_flow._format_user_codes([]) == ""
    assert config_flow._format_user_codes(None) == ""


def test_parse_user_code_input_valid() -> None:
    """Codes should be trimmed and deduplicated."""

    assert config_flow._parse_user_code_input("1234\n 5678\n9012 \n") == [
        "1234",
        "5678",
        "9012",
    ]


def test_parse_user_code_input_invalid() -> None:
    """Duplicate codes should raise :class:`vol.Invalid`."""

    with pytest.raises(vol.Invalid):
        config_flow._parse_user_code_input("1234\n1234")


def test_user_step_schema_defaults() -> None:
    """The schema factory should expose defaults for all fields."""

    schema = config_flow._user_step_schema()
    defaults = schema({})  # type: ignore[call-arg]
    assert defaults["name"] == config_flow.DEFAULT_NAME
    assert defaults["port"] == config_flow.DEFAULT_PORT


def test_user_step_schema_custom_values() -> None:
    """Custom defaults should be honoured by the schema."""

    schema = config_flow._user_step_schema(
        name="Panel", host="example", port=1234, scan_interval=10, sectors=4
    )
    values = schema({})  # type: ignore[call-arg]
    assert values == {
        "name": "Panel",
        "host": "example",
        "port": 1234,
        "scan_interval": 10,
        "sectors": 4,
    }