"""Tests for :class:`closedSpace.operator.MissionRunner`.

Covers ISC-27 (abort → LAND_NOW), ISC-29 (1 Hz progress), and the
happy-path full reference mission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from closedSpace.capture import CaptureSink
from closedSpace.map import load
from closedSpace.mission import plan
from closedSpace.operator import AbortSignal, MissionRunner
from closedSpace.report import ReportBuilder
from closedSpace.storage import LocalSink
from engine.flight_control import ControllerState
from engine.sim import SimCamera, SimFlightController, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def _wire(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Build a fully-wired runner returning everything the tests inspect."""
    m = load(REFERENCE_MAP)
    p = plan(m)

    world = SimWorld()
    bus = InMemoryTelemetryBus()
    fc = SimFlightController(world, bus=bus)
    cam = SimCamera(world)
    SimSLAM(world).start()
    cam.start()

    storage = LocalSink(tmp_path / "m")
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id="m1",
        storage=storage,
        min_capture_resolution_px=256,
        min_focus_score=10.0,
    )
    builder = ReportBuilder(
        mission_id="m1",
        warehouse_id=m.warehouse_id,
        map_id=m.warehouse_id,
        started_utc=datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc),
        planned_capture_count=p.capture_count,
    )
    abort = AbortSignal()
    runner = MissionRunner(
        plan=p, fc=fc, cam=cam, sink=sink, builder=builder,
        bus=bus, abort_signal=abort,
    )
    return runner, fc, bus, abort, p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_full_run_lands_disarmed_with_full_coverage(tmp_path: Path) -> None:
    runner, fc, _bus, _abort, p = _wire(tmp_path)
    result = runner.run()
    assert not result.aborted
    assert fc.get_state() is ControllerState.DISARMED
    assert result.report["captured_waypoints"] == p.capture_count
    assert result.report["coverage_pct"] == 100.0


# ---------------------------------------------------------------------------
# ISC-29 — progress events emitted at the start, per waypoint, and at end
# ---------------------------------------------------------------------------


def test_progress_event_per_waypoint(tmp_path: Path) -> None:
    runner, _fc, bus, _abort, p = _wire(tmp_path)
    progress: list[object] = []
    started: list[object] = []
    finished: list[object] = []
    bus.subscribe("mission.progress", progress.append)
    bus.subscribe("mission.started", started.append)
    bus.subscribe("mission.finished", finished.append)

    runner.run()

    assert len(started) == 1
    assert len(finished) == 1
    # One progress event per executed waypoint.
    assert len(progress) == len(p.waypoints)


# ---------------------------------------------------------------------------
# ISC-27 — abort triggers LAND_NOW; runner returns with aborted=True
# ---------------------------------------------------------------------------


def test_abort_after_takeoff_triggers_landing(tmp_path: Path) -> None:
    """Trigger abort just before the first capture; runner must land and finish."""
    runner, fc, _bus, abort, _p = _wire(tmp_path)
    # Subscribe a stateful trigger: as soon as the controller is airborne,
    # set the abort signal. The runner polls before every waypoint, so it
    # will observe the signal on the next iteration and call land().
    fc.subscribe_state(
        lambda ev: abort.trigger("test-fired") if ev.to_state.value == "airborne" else None
    )

    result = runner.run()

    assert result.aborted
    assert result.abort_reason == "test-fired"
    # Mission must have reached a safe terminal state: DISARMED (post-land)
    # since the runner calls fc.land() on abort while AIRBORNE.
    assert fc.get_state() is ControllerState.DISARMED


def test_abort_before_takeoff_keeps_state_disarmed(tmp_path: Path) -> None:
    """Abort fired before takeoff: runner never arms, stays DISARMED."""
    runner, fc, _bus, abort, _p = _wire(tmp_path)
    abort.trigger("pre-flight abort")
    result = runner.run()
    assert result.aborted
    assert fc.get_state() is ControllerState.DISARMED


# ---------------------------------------------------------------------------
# Side benefit: state transitions tallied for report's telemetry_summary
# ---------------------------------------------------------------------------


def test_state_transitions_recorded_into_report(tmp_path: Path) -> None:
    runner, _fc, _bus, _abort, _p = _wire(tmp_path)
    result = runner.run()
    # disarmed→armed→airborne→landing→disarmed = 4 transitions on the
    # nominal lifecycle.
    assert result.report["telemetry_summary"]["state_transitions"] == 4
