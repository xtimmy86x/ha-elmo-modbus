"""Helpers for parsing and formatting alarm input selections."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

_INPUT_RANGE_PATTERN = re.compile(r"^(?P<start>\d+)\s*-\s*(?P<end>\d+)$")


def _iter_unique_ints(values: Iterable[Any], *, max_value: int) -> list[int]:
    """Return a sorted list of unique integers within the valid range."""

    seen: set[int] = set()
    result: list[int] = []
    for item in values:
        if not isinstance(item, int):
            try:
                item = int(item)  # type: ignore[assignment]
            except (TypeError, ValueError):
                continue
        if item < 1 or item > max_value or item in seen:
            continue
        seen.add(item)
        result.append(item)
    result.sort()
    return result


def parse_input_sensor_selection(value: str, *, max_input: int) -> list[int]:
    """Parse a comma-separated string into a sorted list of alarm inputs."""

    if not value or not value.strip():
        raise ValueError("invalid_input")

    seen: set[int] = set()
    result: list[int] = []

    for part in (piece.strip() for piece in value.replace(";", ",").split(",")):
        if not part:
            continue
        match = _INPUT_RANGE_PATTERN.match(part)
        if match:
            start = int(match.group("start"))
            end = int(match.group("end"))
            range_start = min(start, end)
            range_end = max(start, end)
            if range_start < 1 or range_end > max_input:
                raise ValueError("invalid_input")
            for sensor in range(range_start, range_end + 1):
                if sensor in seen:
                    continue
                seen.add(sensor)
                result.append(sensor)
            continue

        try:
            sensor = int(part)
        except ValueError as err:  # pragma: no cover - defensive guard
            raise ValueError("invalid_input") from err

        if sensor < 1 or sensor > max_input:
            raise ValueError("invalid_input")
        if sensor in seen:
            continue
        seen.add(sensor)
        result.append(sensor)

    if not result:
        raise ValueError("invalid_input")

    result.sort()
    return result


def format_input_sensor_list(inputs: Sequence[int] | None) -> str:
    """Return a compact comma separated representation of alarm inputs."""

    if not inputs:
        return ""

    values = sorted(inputs)
    ranges: list[tuple[int, int]] = []
    start = prev = values[0]

    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append((start, prev))
        start = prev = value

    ranges.append((start, prev))

    parts: list[str] = []
    for range_start, range_end in ranges:
        if range_start == range_end:
            parts.append(str(range_start))
        else:
            parts.append(f"{range_start}-{range_end}")

    return ", ".join(parts)


def normalize_input_sensor_config(value: Any, *, max_input: int) -> list[int]:
    """Normalise stored alarm input configuration into a sorted list."""

    if isinstance(value, int):
        limit = max(1, min(value, max_input))
        return list(range(1, limit + 1))

    if isinstance(value, str):
        try:
            return parse_input_sensor_selection(value, max_input=max_input)
        except ValueError:
            return []

    if isinstance(value, Sequence):
        return _iter_unique_ints(value, max_value=max_input)

    if isinstance(value, set):  # pragma: no cover - compatibility path
        return _iter_unique_ints(value, max_value=max_input)

    return []
