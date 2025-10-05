"""Tests for panel helpers."""

from __future__ import annotations

import importlib

import pytest

panels = importlib.import_module("custom_components.elmo-modbus.panels")
const = importlib.import_module("custom_components.elmo-modbus.const")


def test_sanitize_sectors_filters_values() -> None:
    """Only valid sector identifiers should be retained."""

    result = panels._sanitize_sectors([1, "2", 0, "invalid", 65], max_sector=4)
    assert result == {1, 2}


def test_ensure_unique_slug() -> None:
    """Slug candidates should become unique when necessary."""

    used: set[str] = {"panel", "panel_2"}
    assert panels._ensure_unique_slug("panel", used) == "panel_3"


@pytest.mark.parametrize(
    "raw,expected_modes",
    [
        ({"modes": {"away": [1, 2], "home": [3]}}, {"away": {1, 2}, "home": {3}}),
        ({"modes": {"away": [1, 65]}}, {"away": {1}}),
    ],
)
def test_panel_definition_from_storage(raw, expected_modes) -> None:
    """Stored panel definitions should normalise sectors and slugs."""

    panel = panels.PanelDefinition.from_storage(
        raw,
        used_slugs=set(),
        default_index=1,
        max_sector=64,
    )
    assert panel.modes == expected_modes
    assert panel.slug


def test_panel_definition_from_legacy_defaults() -> None:
    """Legacy options should map to the correct mode settings."""

    options = {
        const.OPTION_ARMED_AWAY_SECTORS: [1, 2, 3],
        const.OPTION_ARMED_HOME_SECTORS: [2],
        const.OPTION_DISARM_SECTORS: [3, 4],
    }
    panel = panels.PanelDefinition.from_legacy(
        options, used_slugs=set(), max_sector=4
    )
    assert panel.modes["away"] == {1, 2, 3}
    assert panel.modes["home"] == {2}
    assert panel.extra_disarm_sectors == {4}


def test_load_panel_definitions_from_storage() -> None:
    """Configured panels should be loaded and normalised."""

    options = {
        const.OPTION_PANELS: [
            {"name": "Panel A", "entity_id_suffix": "panel", "modes": {"away": [1]}},
            {"name": "Panel B", "entity_id_suffix": "panel", "modes": {"home": [2]}},
        ]
    }
    loaded = panels.load_panel_definitions(options, max_sector=4)
    assert len(loaded) == 2
    assert loaded[0].slug == "panel"
    assert loaded[1].slug == "panel_2"


def test_load_panel_definitions_legacy() -> None:
    """Legacy configuration should create a single default panel."""

    options = {}
    loaded = panels.load_panel_definitions(options, max_sector=2)
    assert len(loaded) == 1
    assert loaded[0].modes["away"] == {1, 2}


def test_panels_to_options_roundtrip() -> None:
    """User provided panel data should be converted back to storage format."""

    storage = panels.panels_to_options(
        [
            {"name": "Main", "entity_id_suffix": "main", "modes": {"away": [1, 2]}},
            {"name": "Aux", "entity_id_suffix": "main", "modes": {"home": [3]}},
        ],
        max_sector=4,
    )

    panel_options = storage[const.OPTION_PANELS]
    assert panel_options[0]["entity_id_suffix"] == "main"
    assert panel_options[1]["entity_id_suffix"] == "main_2"