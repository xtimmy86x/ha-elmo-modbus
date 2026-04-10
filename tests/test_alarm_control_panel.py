"""Tests for the alarm control panel helpers."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

alarm_panel = importlib.import_module("custom_components.elmo_modbus.alarm_control_panel")
coordinator = importlib.import_module("custom_components.elmo_modbus.coordinator")

AlarmControlPanelState = importlib.import_module(
    "homeassistant.components.alarm_control_panel"
).AlarmControlPanelState

ElmoModbusAlarmControlPanel = alarm_panel.ElmoModbusAlarmControlPanel
ElmoInventorySnapshot = coordinator.ElmoInventorySnapshot
ElmoPanelStatus = coordinator.ElmoPanelStatus
MODE_TO_STATE = alarm_panel.MODE_TO_STATE


def _build_panel(*, managed: set[int], status: ElmoPanelStatus | None, span: int) -> ElmoModbusAlarmControlPanel:
    panel = object.__new__(ElmoModbusAlarmControlPanel)
    panel._managed_sectors = managed  # type: ignore[attr-defined]
    snapshot = ElmoInventorySnapshot(
        status=status,
        discrete_inputs={},
        coils={},
        holding_registers={},
    )
    panel.coordinator = SimpleNamespace(data=snapshot, sector_count=span)  # type: ignore[attr-defined]
    return panel


def _build_state_panel(
    *,
    managed: set[int],
    armed_bits: tuple[bool, ...],
    triggered_bits: tuple[bool, ...] | None = None,
    mode_sectors: dict[str, set[int]] | None = None,
    discrete_inputs: dict[int, bool] | None = None,
) -> ElmoModbusAlarmControlPanel:
    """Helper to build a panel with mode_sectors for alarm_state tests."""
    span = len(armed_bits)
    if triggered_bits is None:
        triggered_bits = tuple(False for _ in armed_bits)
    status = ElmoPanelStatus(armed=armed_bits, triggered=triggered_bits)
    snapshot = ElmoInventorySnapshot(
        status=status,
        discrete_inputs=discrete_inputs or {},
        coils={},
        holding_registers={},
    )
    panel = object.__new__(ElmoModbusAlarmControlPanel)
    panel._managed_sectors = managed
    panel.coordinator = SimpleNamespace(data=snapshot, sector_count=span)
    if mode_sectors is None:
        mode_sectors = {}
    panel._mode_sectors = {
        mode: sectors for mode, sectors in mode_sectors.items()
    }
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


# ── alarm_state priority tests ──────────────────────────────────────────


def test_armed_away_priority_when_all_away_sectors_active() -> None:
    """armed_away should activate when all its configured sectors are armed,
    even if extra sectors are also armed."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4},
        armed_bits=(True, True, True, True),
        mode_sectors={"away": {1, 2, 3, 4}, "home": {1, 2}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_AWAY


def test_armed_away_priority_superset_of_other_modes() -> None:
    """armed_away takes priority even when armed sectors also fully cover
    another mode's sectors."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4},
        armed_bits=(True, True, True, False),
        mode_sectors={"away": {1, 2, 3}, "night": {1, 2, 3}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_AWAY


def test_armed_away_with_extra_sectors_armed() -> None:
    """armed_away should be returned when all away sectors are armed,
    plus additional sectors outside any mode."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4, 5},
        armed_bits=(True, True, True, True, True),
        mode_sectors={"away": {1, 2, 3}, "home": {4, 5}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_AWAY


def test_armed_home_when_away_sectors_not_fully_armed() -> None:
    """If not all away sectors are armed, other modes can still match exactly."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4},
        armed_bits=(True, True, False, False),
        mode_sectors={"away": {1, 2, 3, 4}, "home": {1, 2}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_HOME


def test_disarmed_when_no_sectors_armed() -> None:
    """Panel with no sectors armed should be DISARMED."""

    panel = _build_state_panel(
        managed={1, 2, 3},
        armed_bits=(False, False, False),
        mode_sectors={"away": {1, 2, 3}},
    )

    assert panel.alarm_state == AlarmControlPanelState.DISARMED


# ── additional alarm_state coverage ─────────────────────────────────────


def test_alarm_state_none_when_no_snapshot() -> None:
    """alarm_state returns None when coordinator has no data."""

    panel = object.__new__(ElmoModbusAlarmControlPanel)
    panel._managed_sectors = set()
    panel.coordinator = SimpleNamespace(data=None, sector_count=4)
    panel._mode_sectors = {}

    assert panel.alarm_state is None


def test_alarm_state_none_when_status_is_none() -> None:
    """alarm_state returns None when snapshot has no status."""

    snapshot = ElmoInventorySnapshot(
        status=None, discrete_inputs={}, coils={}, holding_registers={},
    )
    panel = object.__new__(ElmoModbusAlarmControlPanel)
    panel._managed_sectors = set()
    panel.coordinator = SimpleNamespace(data=snapshot, sector_count=4)
    panel._mode_sectors = {}

    assert panel.alarm_state is None


def test_triggered_when_general_alarm_active() -> None:
    """TRIGGERED is returned when armed sectors are triggered and general
    alarm discrete input (0x0200) is True."""

    panel = _build_state_panel(
        managed={1, 2, 3},
        armed_bits=(True, True, False),
        triggered_bits=(True, False, False),
        mode_sectors={"away": {1, 2, 3}},
        discrete_inputs={0x0200: True},
    )

    assert panel.alarm_state == AlarmControlPanelState.TRIGGERED


def test_not_triggered_without_general_alarm() -> None:
    """Even with triggered sectors, if general alarm input is not set
    the panel should not report TRIGGERED."""

    panel = _build_state_panel(
        managed={1, 2, 3},
        armed_bits=(True, True, False),
        triggered_bits=(True, False, False),
        mode_sectors={"away": {1, 2, 3}},
        discrete_inputs={0x0200: False},
    )

    assert panel.alarm_state != AlarmControlPanelState.TRIGGERED


def test_all_sectors_armed_falls_back_to_away() -> None:
    """When all panel sectors are armed but no exact mode match,
    the state should be ARMED_AWAY."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4},
        armed_bits=(True, True, True, True),
        mode_sectors={"home": {1, 2}, "night": {3, 4}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_AWAY


def test_exact_match_takes_precedence_over_partial() -> None:
    """An exact match for a non-away mode takes precedence over a
    partial superset match for away."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4, 5},
        armed_bits=(True, True, True, False, False),
        mode_sectors={"away": {1, 2, 3, 4, 5}, "night": {1, 2, 3}},
    )

    # night matches exactly, away only partially → exact match wins
    assert panel.alarm_state == AlarmControlPanelState.ARMED_NIGHT


def test_partial_overlap_higher_priority_wins() -> None:
    """When no exact match, the mode with the most overlap wins;
    priority breaks ties."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4, 5, 6},
        armed_bits=(True, True, False, True, False, False),
        mode_sectors={"home": {1, 2, 3}, "night": {1, 4, 5}},
    )

    # home overlaps 2 sectors ({1,2}), night overlaps 2 ({1,4})
    # equal overlap → priority tiebreaker: night(2) > home(1)
    assert panel.alarm_state == AlarmControlPanelState.ARMED_NIGHT


def test_armed_custom_bypass_when_no_mode_matches() -> None:
    """ARMED_CUSTOM_BYPASS is returned when sectors are armed but no
    configured profile matches at all."""

    panel = _build_state_panel(
        managed={1, 2, 3, 4},
        armed_bits=(True, False, False, False),
        mode_sectors={"away": {2, 3, 4}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_CUSTOM_BYPASS


def test_unmanaged_panel_uses_all_bits() -> None:
    """A panel with no managed sectors should consider all armed bits."""

    panel = _build_state_panel(
        managed=set(),
        armed_bits=(True, True, True, True),
        mode_sectors={"away": {1, 2, 3, 4}},
    )

    assert panel.alarm_state == AlarmControlPanelState.ARMED_AWAY