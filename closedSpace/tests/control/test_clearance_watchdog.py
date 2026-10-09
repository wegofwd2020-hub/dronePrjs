"""Tests for :class:`closedSpace.control.ClearanceWatchdog`.

Covers the seven ISC-14/33/31 assertions: safe clearance no-op,
violation fires SAFE_HOVER + COLLISION event, geofence exemption,
ground states skip check, exact threshold boundary, sensor exception
treated as violation, and optional watchdog in full mission run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from closedSpace.capture import CaptureSink
from closedSpace.constants import MIN_CLEARANCE_M
from closedSpace.control import ClearanceWatchdog
from closedSpace.map import load
from closedSpace.mission import MissionConfig, plan
from closedSpace.operator import MissionRunner
from closedSpace.report import ReportBuilder
from closedSpace.storage import LocalSink
from engine.flight_control import ControllerState
from engine.sim import (
    SimCamera,
    SimFlightController,
    SimProximitySensor,
    SimSLAM,
    SimWorld,
)
from engine.telemetry import InMemoryTelemetryBus

REFERENCE_MAP = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)

_STARTED = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeClock:
    """Manual monotonic-ns clock; advance() lets tests control time."""

    def __init__(self, start_ns: int = 0) -> None:
        self._t = start_ns

    def advance(self, ns: int) -> None:
        self._t += ns

    def __call__(self) -> int:
        return self._t


def _make_watchdog(
    default_clearance_m: float = 2.0,
    bus: InMemoryTelemetryBus | None = None,
) -> tuple[_FakeClock, SimFlightController, SimProximitySensor]:
    clock = _FakeClock()
    world = SimWorld(clock=clock)
    fc = SimFlightController(world, bus=bus)
    sensor = SimProximitySensor(world, default_clearance_m=default_clearance_m)
    return clock, fc, sensor


def _airborne(fc: SimFlightController, z: float = 3.0) -> None:
    fc.arm()
    fc.takeoff(z)


# ---------------------------------------------------------------------------
# 1. Safe clearance → no transition; control.clearance event with violation=False
# ---------------------------------------------------------------------------


def test_safe_clearance_no_transition() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, sensor = _make_watchdog(default_clearance_m=2.0, bus=bus)
    _airborne(fc)
    events: list[dict] = []
    bus.subscribe("control.clearance", events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE
    assert len(events) == 1
    assert events[0]["payload"]["violation"] is False


# ---------------------------------------------------------------------------
# 2. Violation → SAFE_HOVER + COLLISION event; clearance event with violation=True
# ---------------------------------------------------------------------------


def test_violation_fires_safe_hover_and_collision_event() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, sensor = _make_watchdog(default_clearance_m=0.3, bus=bus)
    _airborne(fc)
    collision_events: list[dict] = []
    clearance_events: list[dict] = []
    bus.subscribe("control.collision", collision_events.append)
    bus.subscribe("control.clearance", clearance_events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.SAFE_HOVER
    assert len(collision_events) == 1
    assert collision_events[0]["payload"]["severity"] == "COLLISION"
    assert len(clearance_events) == 1
    assert clearance_events[0]["payload"]["violation"] is True


# ---------------------------------------------------------------------------
# 3. Geofence exemption — z < CLEARANCE_GEOFENCE_HEIGHT_M skips check; no events
# ---------------------------------------------------------------------------


def test_geofence_exemption_skips_check() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, sensor = _make_watchdog(default_clearance_m=0.1, bus=bus)
    # takeoff to z=0.5 which is below CLEARANCE_GEOFENCE_HEIGHT_M (1.0)
    _airborne(fc, z=0.5)
    events: list[dict] = []
    bus.subscribe("control.clearance", events.append)
    bus.subscribe("control.collision", events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE
    assert len(events) == 0


# ---------------------------------------------------------------------------
# 4. Ground states skip check — DISARMED and ARMED both no-op; no events
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grounded", [ControllerState.DISARMED, ControllerState.ARMED])
def test_ground_states_skip_check(grounded: ControllerState) -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, sensor = _make_watchdog(default_clearance_m=0.1, bus=bus)
    if grounded is ControllerState.ARMED:
        fc.arm()
    events: list[dict] = []
    bus.subscribe("control.clearance", events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is grounded
    assert len(events) == 0


# ---------------------------------------------------------------------------
# 5. Exact threshold is safe — strict < guard; no COLLISION event
# ---------------------------------------------------------------------------


def test_exact_threshold_is_safe() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, sensor = _make_watchdog(default_clearance_m=MIN_CLEARANCE_M, bus=bus)
    _airborne(fc)
    collision_events: list[dict] = []
    bus.subscribe("control.collision", collision_events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE
    assert len(collision_events) == 0


# ---------------------------------------------------------------------------
# 6. Sensor raises → treated as violation; fc → SAFE_HOVER, COLLISION emitted
# ---------------------------------------------------------------------------


class _RaisingSensor(SimProximitySensor):
    def min_clearance_m(self) -> float:
        raise RuntimeError("sensor hardware fault")


def test_sensor_exception_treated_as_violation() -> None:
    bus = InMemoryTelemetryBus()
    clock = _FakeClock()
    world = SimWorld(clock=clock)
    fc = SimFlightController(world, bus=bus)
    sensor = _RaisingSensor(world)
    _airborne(fc)
    collision_events: list[dict] = []
    bus.subscribe("control.collision", collision_events.append)

    watchdog = ClearanceWatchdog(sensor=sensor, fc=fc, bus=bus, clock=clock)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.SAFE_HOVER
    assert len(collision_events) == 1


# ---------------------------------------------------------------------------
# 7. Optional watchdog — MissionRunner with clearance_watchdog=None runs clean
# ---------------------------------------------------------------------------


def test_runner_without_clearance_watchdog_runs_full_mission(tmp_path: Path) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m, MissionConfig())
    world = SimWorld()
    fc = SimFlightController(world)
    slam = SimSLAM(world)
    cam = SimCamera(world)
    slam.start()
    cam.start()
    storage = LocalSink(tmp_path / "lap-0")
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id="lap-0",
        storage=storage,
        min_capture_resolution_px=256,
        min_focus_score=10.0,
    )
    builder = ReportBuilder(
        mission_id="lap-0",
        warehouse_id=m.warehouse_id,
        map_id=m.warehouse_id,
        started_utc=_STARTED,
        planned_capture_count=p.capture_count,
    )
    result = MissionRunner(
        plan=p,
        fc=fc,
        cam=cam,
        sink=sink,
        builder=builder,
        clearance_watchdog=None,
    ).run()
    assert not result.aborted
