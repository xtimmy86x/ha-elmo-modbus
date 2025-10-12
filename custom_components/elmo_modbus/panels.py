"""Helpers for handling panel configurations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from homeassistant.util import slugify

from .const import (
    DEFAULT_SECTORS,
    OPTION_ARMED_AWAY_SECTORS,
    OPTION_ARMED_HOME_SECTORS,
    OPTION_ARMED_NIGHT_SECTORS,
    OPTION_DISARM_SECTORS,
    OPTION_PANELS,
)

LEGACY_OPTION_MAP = {
    "away": OPTION_ARMED_AWAY_SECTORS,
    "home": OPTION_ARMED_HOME_SECTORS,
    "night": OPTION_ARMED_NIGHT_SECTORS,
}

MODES: tuple[str, ...] = tuple(LEGACY_OPTION_MAP)


def _sanitize_sectors(
    values: Iterable[Any] | None, *, max_sector: int = DEFAULT_SECTORS
) -> set[int]:
    """Return a sanitised set of sector identifiers."""

    result: set[int] = set()
    if not values:
        return result

    for value in values:
        try:
            sector = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= sector <= max_sector:
            result.add(sector)

    return result


def _ensure_unique_slug(candidate: str, used: set[str]) -> str:
    """Ensure the slug is unique among the provided set."""

    base = candidate or "panel"
    slug = base
    index = 2

    while slug in used:
        slug = f"{base}_{index}"
        index += 1

    used.add(slug)
    return slug


@dataclass
class PanelDefinition:
    """Normalised representation of a panel configuration."""

    name: str
    slug: str
    modes: dict[str, set[int]] = field(default_factory=dict)
    extra_disarm_sectors: set[int] = field(default_factory=set)

    def mode_sectors(self, mode: str) -> set[int]:
        """Return the configured sectors for a mode."""

        return set(self.modes.get(mode, set()))

    @property
    def managed_sectors(self) -> set[int]:
        """Return the union of all sectors controller DEFAULT_SECTORS by the panel."""

        sectors: set[int] = set()
        for mode_sectors in self.modes.values():
            sectors.update(mode_sectors)
        sectors.update(self.extra_disarm_sectors)
        return sectors

    def to_storage(self) -> dict[str, Any]:
        """Return a serialisable representation for config entry options."""

        return {
            "name": self.name,
            "entity_id_suffix": self.slug,
            "modes": {
                mode: sorted(sectors) for mode, sectors in self.modes.items() if sectors
            },
        }

    @classmethod
    def from_storage(
        cls,
        raw: Mapping[str, Any],
        *,
        used_slugs: set[str],
        default_index: int,
        max_sector: int = DEFAULT_SECTORS,
    ) -> PanelDefinition:
        """Create a panel definition from stored options."""

        name = str(raw.get("name") or f"Panel {default_index}")
        slug_value = str(raw.get("entity_id_suffix") or "").strip()
        slug_candidate = slugify(slug_value) if slug_value else slugify(name)
        slug = _ensure_unique_slug(
            slug_candidate or f"panel_{default_index}", used_slugs
        )

        modes_data = raw.get("modes", {})
        modes: dict[str, set[int]] = {}
        for mode in MODES:
            sectors = _sanitize_sectors(modes_data.get(mode), max_sector=max_sector)
            if sectors:
                modes[mode] = sectors

        return cls(name=name, slug=slug, modes=modes)

    @classmethod
    def from_legacy(
        cls,
        options: Mapping[str, Any],
        *,
        used_slugs: set[str],
        max_sector: int = DEFAULT_SECTORS,
    ) -> PanelDefinition:
        """Create a panel definition from legacy options."""

        name = "Alarm Panel"
        slug = _ensure_unique_slug(slugify(name) or "alarm_panel", used_slugs)

        modes: dict[str, set[int]] = {}
        for mode, option_key in LEGACY_OPTION_MAP.items():
            sectors = _sanitize_sectors(options.get(option_key), max_sector=max_sector)
            if sectors:
                modes[mode] = sectors

        disarm_sectors = _sanitize_sectors(
            options.get(OPTION_DISARM_SECTORS), max_sector=max_sector
        )

        if not modes:
            # Old behaviour armed all sectors when
            # no specific configuration was provided.
            modes["away"] = set(range(1, max_sector + 1))

        if disarm_sectors:
            extra = disarm_sectors - modes.get("away", set())
        else:
            extra = set()

        return cls(
            name=name,
            slug=slug,
            modes=modes,
            extra_disarm_sectors=extra,
        )


def load_panel_definitions(
    options: Mapping[str, Any], *, max_sector: int = DEFAULT_SECTORS
) -> list[PanelDefinition]:
    """Return the configured panels for the given options mapping."""

    used_slugs: set[str] = set()

    if OPTION_PANELS in options:
        raw_panels = options.get(OPTION_PANELS, [])
        panels: list[PanelDefinition] = []
        if isinstance(raw_panels, Sequence):
            for index, raw in enumerate(raw_panels, start=1):
                if isinstance(raw, Mapping):
                    panels.append(
                        PanelDefinition.from_storage(
                            raw,
                            used_slugs=used_slugs,
                            default_index=index,
                            max_sector=max_sector,
                        )
                    )
        return panels

    # Legacy single-panel configuration.
    return [
        PanelDefinition.from_legacy(
            options, used_slugs=used_slugs, max_sector=max_sector
        )
    ]


def panels_to_options(
    raw_panels: Sequence[Mapping[str, Any]], *, max_sector: int = DEFAULT_SECTORS
) -> dict[str, Any]:
    """Normalise user-provided panels and return the options payload."""

    used_slugs: set[str] = set()
    panels: list[PanelDefinition] = []
    for index, raw in enumerate(raw_panels, start=1):
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or f"Panel {index}")
        slug_value = str(raw.get("entity_id_suffix") or "").strip()
        slug_candidate = slugify(slug_value) if slug_value else slugify(name)
        slug = _ensure_unique_slug(slug_candidate or f"panel_{index}", used_slugs)

        modes: dict[str, set[int]] = {}
        modes_data = raw.get("modes", {})
        for mode in MODES:
            sectors = _sanitize_sectors(modes_data.get(mode), max_sector=max_sector)
            if sectors:
                modes[mode] = sectors

        panels.append(PanelDefinition(name=name, slug=slug, modes=modes))

    return {OPTION_PANELS: [panel.to_storage() for panel in panels]}
