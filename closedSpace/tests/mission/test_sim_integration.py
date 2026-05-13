"""Phase 2 exit-criterion probe: plan → sim end-to-end.

This is a smoke-level integration test, not the full mission runner.
It proves the wiring: every waypoint in a plan can be commanded to the
:class:`engine.sim.SimFlightController`, SLAM and Camera see the
expected pose, and telemetry events fan out to a JSONL log.

The "real" mission runner lives in Phase 4 (capture + storage + report).
This test guards the Protocol surface — if Phase 2 abstractions break,
this test fails first.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from closedSpace.map import load
from closedSpace.mission import Waypoint, plan
from engine.flight_control import ControllerState
from engine.sim import SimCamera, SimFlightController, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus, JSONLTelemetryLogger

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def _execute_waypoint(
    fc: SimFlightController, cam: SimCamera, wp: Waypoint, takeoff_height_m: float
) -> tuple[int, int]:
    """Drive one waypoint through the sim. Returns (captures, gotos)."""
    if wp.kind == "takeoff":
        fc.arm()
        fc.takeoff(takeoff_height_m)
        return (0, 0)
    if wp.kind == "landing":
        fc.land()
        return (0, 0)
    fc.goto(wp.x, wp.y, wp.z, wp.yaw_deg)
    if wp.capture:
        cam.capture(fc.get_pose())
        return (1, 1)
    return (0, 1)


def test_end_to_end_reference_mission(tmp_path: Path) -> None:
    """Every plan waypoint reaches the sim; final state is DISARMED."""
    m = load(REFERENCE_MAP)
    p = plan(m)

    world = SimWorld()
    bus = InMemoryTelemetryBus()
    fc = SimFlightController(world, bus=bus)
    slam = SimSLAM(world)
    cam = SimCamera(world)
    slam.start()
    cam.start()

    log_path = tmp_path / "telemetry.jsonl"
    captures = 0
    gotos = 0
    with JSONLTelemetryLogger(log_path) as logger:
        logger.attach(bus, "flight_control.state")
        for wp in p.waypoints:
            c, g = _execute_waypoint(
                fc, cam, wp, takeoff_height_m=p.waypoints[0].z
            )
            captures += c
            gotos += g

    assert fc.get_state() is ControllerState.DISARMED
    assert captures == p.capture_count
    # 1 takeoff + (waypoints - 2 non-goto) gotos + 1 landing accounts for the
    # full list; goto count = waypoints - 2 (takeoff & landing).
    assert gotos == len(p.waypoints) - 2

    # SLAM agreed with the final commanded pose (sim is zero-error).
    final_pose = slam.get_pose()
    assert final_pose.z == pytest.approx(0.0)  # landed

    # Telemetry log has the four lifecycle transitions at minimum.
    lines = log_path.read_text().splitlines()
    transitions = [json.loads(ln) for ln in lines]
    to_states = [t["payload"]["to"] for t in transitions]
    assert to_states[:2] == ["armed", "airborne"]
    assert to_states[-2:] == ["landing", "disarmed"]


def test_slam_pose_tracks_first_capture_waypoint() -> None:
    """After the first capture goto, SLAM reports that exact pose."""
    m = load(REFERENCE_MAP)
    p = plan(m)
    first_capture = next(w for w in p.waypoints if w.capture)

    world = SimWorld()
    fc = SimFlightController(world)
    slam = SimSLAM(world)
    slam.start()
    fc.arm()
    fc.takeoff(p.waypoints[0].z)
    # Walk through preceding non-capture waypoints (skip takeoff).
    for wp in p.waypoints[1:]:
        if wp.capture:
            break
        if wp.kind == "transit":
            fc.goto(wp.x, wp.y, wp.z, wp.yaw_deg)
    fc.goto(
        first_capture.x, first_capture.y, first_capture.z, first_capture.yaw_deg
    )

    pose = slam.get_pose()
    assert (pose.x, pose.y, pose.z, pose.yaw_deg) == (
        first_capture.x,
        first_capture.y,
        first_capture.z,
        first_capture.yaw_deg,
    )
