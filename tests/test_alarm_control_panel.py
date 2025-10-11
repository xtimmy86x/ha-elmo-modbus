"""Tests for the alarm control panel helpers."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

alarm_panel = importlib.import_module("custom_components.elmo-modbus.alarm_control_panel")
coordinator = importlib.import_module("custom_components.elmo-modbus.coordinator")

ElmoModbusAlarmControlPanel = alarm_panel.ElmoModbusAlarmControlPanel
ElmoPanelStatus = coordinator.ElmoPanelStatus


def _build_panel(*, managed: set[int], status: ElmoPanelStatus | None, span: int) -> ElmoModbusAlarmControlPanel:
    panel = object.__new__(ElmoModbusAlarmControlPanel)
    panel._managed_sectors = managed  # type: ignore[attr-defined]
    panel.coordinator = SimpleNamespace(data=status, sector_count=span)  # type: ignore[attr-defined]
    return panel


def test_build_command_payload_limits_to_managed_sectors() -> None:
    """Only sectors managed by the panel should be affected."""

    status = ElmoPanelStatus(
        armed=(True, True, False, True, False),
        triggered=(False, False, False, False, False),
    )
    panel = _build_panel(managed={1, 3, 4}, status=status, span=5)

    payload = panel._build_command_payload([3], value=True)

    assert payload == [False, True, True, False, False]


def test_build_command_payload_without_status_defaults_to_scope() -> None:
    """When no status is available, the scope is derived from the coordinator."""

    panel = _build_panel(managed=set(), status=None, span=4)

    payload = panel._build_command_payload([2, 4], value=True)

    assert payload == [False, True, False, True]