"""Tests for ``custom_components.elmo_modbus.input_selectors``."""

from __future__ import annotations

import importlib

import pytest

input_selectors = importlib.import_module(
    "custom_components.elmo_modbus.input_selectors"
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", [1]),
        ("1,2,3", [1, 2, 3]),
        ("1-3", [1, 2, 3]),
        ("3-1", [1, 2, 3]),
        ("1, 2-4, 4, 5", [1, 2, 3, 4, 5]),
        ("1;2", [1, 2]),
        ("1 , 3-5", [1, 3, 4, 5]),
    ],
)
def test_parse_input_sensor_selection_valid(value: str, expected: list[int]) -> None:
    """Valid selections should be parsed into sorted integers."""

    assert input_selectors.parse_input_sensor_selection(value, max_input=64) == expected


@pytest.mark.parametrize(
    "value",
    ["", "   ", "0", "65", "1, abc", "1, 2-100", "-1", "1-", "-2--1"],
)
def test_parse_input_sensor_selection_invalid(value: str) -> None:
    """Invalid selections raise a :class:`ValueError`."""

    with pytest.raises(ValueError):
        input_selectors.parse_input_sensor_selection(value, max_input=64)


@pytest.mark.parametrize(
    "inputs,expected",
    [
        ([], ""),
        ([1], "1"),
        ([1, 2, 3], "1-3"),
        ([1, 3, 4, 6, 7, 8], "1, 3-4, 6-8"),
        ([5, 2, 3, 4, 1], "1-5"),
    ],
)
def test_format_input_sensor_list(inputs: list[int], expected: str) -> None:
    """The formatting helper should compact consecutive ranges."""

    assert input_selectors.format_input_sensor_list(inputs) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (5, [1, 2, 3, 4, 5]),
        ("1,3-4", [1, 3, 4]),
        (["2", 3, 3, 5], [2, 3, 5]),
        ({1, 1, 2, 4}, [1, 2, 4]),
        ("", []),
        (None, []),
    ],
)
def test_normalize_input_sensor_config(value, expected) -> None:
    """Normalisation should support integers, strings and iterables."""

    assert input_selectors.normalize_input_sensor_config(value, max_input=5) == expected


def test_normalize_input_sensor_config_out_of_range() -> None:
    """Out-of-range entries are ignored when normalising iterables."""

    assert input_selectors.normalize_input_sensor_config([0, 1, 6], max_input=5) == [1]