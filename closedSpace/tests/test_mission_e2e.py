"""Phase 4 exit-criterion probe: plan → sim → capture → storage → report.

This is the "full stack" smoke for the closedSpace mission pipeline,
end-to-end, with no real hardware. The test:

1. Loads the reference map and plans the mission.
2. Runs every waypoint through the SimFlightController + SimCamera.
3. Hands each captured Frame to CaptureSink, which writes image + sidecar
   under a temp mission root via LocalSink.
4. Builds the mission report, validates it against the JSON Schema,
   and re-asserts the headline fields (capture count, coverage_pct,
   schema conformance).

Gate thresholds are dialed down to sim-sized values — the goal here is
pipeline correctness, not real-hardware verification (ISC-19, ISC-20
remain Phase 8 / pilot probes).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from closedSpace.capture import CaptureRecorded, CaptureSink
from closedSpace.map import load
from closedSpace.mission import Waypoint, plan
from closedSpace.report import ReportBuilder, validate_report
from closedSpace.storage import LocalSink
from engine.flight_control import ControllerState
from engine.sim import SimCamera, SimFlightController, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus

REFERENCE_MAP = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def _drive(
    fc: SimFlightController,
    cam: SimCamera,
    sink: CaptureSink,
    report: ReportBuilder,
    waypoints: tuple[Waypoint, ...],
    takeoff_height_m: float,
) -> None:
    for wp in waypoints:
        if wp.kind == "takeoff":
            fc.arm()
            fc.takeoff(takeoff_height_m)
            continue
        if wp.kind == "landing":
            fc.land()
            continue
        fc.goto(wp.x, wp.y, wp.z, wp.yaw_deg)
        if wp.capture:
            frame = cam.capture(fc.get_pose())
            report.record(sink.consume(wp, frame))


def test_full_pipeline_against_reference(tmp_path: Path) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m)

    world = SimWorld()
    bus = InMemoryTelemetryBus()
    fc = SimFlightController(world, bus=bus)
    slam = SimSLAM(world)
    cam = SimCamera(world)
    slam.start()
    cam.start()

    # Tally state transitions for the telemetry summary.
    transitions: list[object] = []
    bus.subscribe("flight_control.state", transitions.append)

    storage = LocalSink(tmp_path / "missions" / "m-2026-05-13")
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id="m-2026-05-13",
        storage=storage,
        # Sim emits 16×16 grayscale; loosen the gates so the pipeline
        # actually exercises the success path.
        min_capture_resolution_px=256,
        min_focus_score=10.0,
        clock=lambda: datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc),
    )

    builder = ReportBuilder(
        mission_id="m-2026-05-13",
        warehouse_id=m.warehouse_id,
        map_id=m.warehouse_id,
        started_utc=datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc),
        planned_capture_count=p.capture_count,
    )

    _drive(fc, cam, sink, builder, p.waypoints, takeoff_height_m=p.waypoints[0].z)

    for _ in transitions:
        builder.record_state_transition()

    report = builder.finalize(
        finished_utc=datetime(2026, 5, 13, 10, 5, 0, tzinfo=timezone.utc)
    )

    # ISC-16: one image per declared capture waypoint.
    images = sorted((tmp_path / "missions" / "m-2026-05-13").rglob("*.jpg"))
    assert len(images) == p.capture_count
    # Co-located sidecars (ISC-17).
    sidecars = sorted((tmp_path / "missions" / "m-2026-05-13").rglob("*.jpg.json"))
    assert len(sidecars) == p.capture_count

    # ISC-23 / ISC-24 / ISC-25: report fields, exact coverage, schema validates.
    assert report["captured_waypoints"] == p.capture_count
    assert report["coverage_pct"] == 100.0
    validate_report(report)  # re-assert from outside the builder

    # Mission ends DISARMED, telemetry counted four lifecycle transitions
    # (disarmed→armed→airborne→landing→disarmed).
    assert fc.get_state() is ControllerState.DISARMED
    assert report["telemetry_summary"]["state_transitions"] == 4


def test_sidecar_records_the_captured_pose(tmp_path: Path) -> None:
    """The §ISC-17 sidecar pose MUST agree with the commanded waypoint."""
    m = load(REFERENCE_MAP)
    p = plan(m)
    first_capture = next(w for w in p.waypoints if w.capture)

    world = SimWorld()
    fc = SimFlightController(world)
    cam = SimCamera(world)
    cam.start()

    storage = LocalSink(tmp_path / "m")
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id="m1",
        storage=storage,
        min_capture_resolution_px=256,
        min_focus_score=10.0,
    )

    fc.arm()
    fc.takeoff(p.waypoints[0].z)
    # Hop directly to the first capture waypoint (planner correctness
    # is verified elsewhere; here we exercise the sidecar contract).
    fc.goto(
        first_capture.x, first_capture.y, first_capture.z, first_capture.yaw_deg
    )
    frame = cam.capture(fc.get_pose())
    outcome = sink.consume(first_capture, frame)
    assert isinstance(outcome, CaptureRecorded)

    side = json.loads(outcome.artifact.sidecar_path.read_text())
    assert side["pose"] == {
        "x": first_capture.x,
        "y": first_capture.y,
        "z": first_capture.z,
        "yaw_deg": first_capture.yaw_deg,
    }
    assert side["aisle_id"] == first_capture.metadata["aisle_id"]
    assert side["rack_id"] == first_capture.metadata["rack_id"]
    assert side["level_index"] == first_capture.metadata["level_index"]
