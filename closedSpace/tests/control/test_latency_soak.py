"""ISC-13 soak tests — LatencyRecorder wired into MissionRunner.

Covers the four runner-integration assertions (pure LatencyRecorder
unit tests live in test_latency.py, the ISC-41 mirror for latency.py):

1. Soak passes p99  — 3 laps → ≥ 200 samples; p99 < 50 ms.
2. Sample count     — completed waypoints == len(recorder.samples).
3. Event published  — control.latency bus event per completed waypoint.
4. Recorder optional— runner with recorder=None runs without error.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from closedSpace.capture import CaptureSink
from closedSpace.constants import PERCEPTION_CMD_LATENCY_P99_S
from closedSpace.control import LatencyRecorder
from closedSpace.map import load
from closedSpace.mission import MissionConfig, plan
from closedSpace.operator import MissionRunner
from closedSpace.report import ReportBuilder
from closedSpace.storage import LocalSink
from engine.sim import SimCamera, SimFlightController, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus

REFERENCE_MAP = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)

_STARTED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_runner(
    tmp_path: Path,
    lap: int,
    recorder: LatencyRecorder | None = None,
    bus: InMemoryTelemetryBus | None = None,
) -> MissionRunner:
    m = load(REFERENCE_MAP)
    p = plan(m, MissionConfig())
    world = SimWorld()
    fc = SimFlightController(world, bus=bus)
    slam = SimSLAM(world)
    cam = SimCamera(world)
    slam.start()
    cam.start()
    storage = LocalSink(tmp_path / f"lap-{lap}")
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id=f"lap-{lap}",
        storage=storage,
        min_capture_resolution_px=256,
        min_focus_score=10.0,
    )
    builder = ReportBuilder(
        mission_id=f"lap-{lap}",
        warehouse_id=m.warehouse_id,
        map_id=m.warehouse_id,
        started_utc=_STARTED,
        planned_capture_count=p.capture_count,
    )
    return MissionRunner(
        plan=p,
        fc=fc,
        cam=cam,
        sink=sink,
        builder=builder,
        bus=bus,
        recorder=recorder,
    )


# ---------------------------------------------------------------------------
# 1. Soak passes p99 — 3 laps → ≥ 200 samples; p99 < 50 ms
# ---------------------------------------------------------------------------


def test_soak_p99_under_budget(tmp_path: Path) -> None:
    recorder = LatencyRecorder()
    for lap in range(3):
        _make_runner(tmp_path, lap, recorder=recorder).run()

    assert len(recorder.samples) >= 200
    assert recorder.p99_s() < PERCEPTION_CMD_LATENCY_P99_S


# ---------------------------------------------------------------------------
# 2. Sample count — completed waypoints == len(recorder.samples)
# ---------------------------------------------------------------------------


def test_sample_count_matches_waypoints(tmp_path: Path) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m, MissionConfig())
    recorder = LatencyRecorder()
    _make_runner(tmp_path, 0, recorder=recorder).run()

    assert len(recorder.samples) == len(p.waypoints)


# ---------------------------------------------------------------------------
# 3. Event published — control.latency per completed waypoint, has latency_ns
# ---------------------------------------------------------------------------


def test_latency_event_published_per_waypoint(tmp_path: Path) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m, MissionConfig())
    bus = InMemoryTelemetryBus()
    recorder = LatencyRecorder()
    events: list[dict] = []
    bus.subscribe("control.latency", events.append)

    _make_runner(tmp_path, 0, recorder=recorder, bus=bus).run()

    assert len(events) == len(p.waypoints)
    for ev in events:
        assert ev["topic"] == "control.latency"
        assert "latency_ns" in ev["payload"]
        assert isinstance(ev["payload"]["latency_ns"], int)


# ---------------------------------------------------------------------------
# 4. Recorder optional — recorder=None (default) runs full mission cleanly
# ---------------------------------------------------------------------------


def test_runner_without_recorder_runs_clean(tmp_path: Path) -> None:
    result = _make_runner(tmp_path, 0, recorder=None).run()
    assert not result.aborted
