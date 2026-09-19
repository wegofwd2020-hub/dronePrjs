"""Unit tests for the engine.sim stubs and shared helpers.

Covers:
* Protocol conformance via ``isinstance`` against ``runtime_checkable``.
* State-machine transitions and illegal-transition errors.
* Telemetry pub/sub fan-out and event shape.
* SimCamera determinism (same pose → identical bytes & focus score).
* Laplacian focus score basic properties (uniform → 0, structured > 0).
"""
from __future__ import annotations

import pytest

from engine.flight_control import ControllerState, FlightController, StateChange
from engine.link import LinkMonitor
from engine.localization import SLAMProvider
from engine.sensors import Camera, laplacian_focus_score
from engine.sim import (
    SimCamera,
    SimFlightController,
    SimLinkMonitor,
    SimSLAM,
    SimWorld,
)
from engine.telemetry import InMemoryTelemetryBus
from engine.types import Pose


# ---------------------------------------------------------------------------
# Protocol conformance — pins the engine's structural contract
# ---------------------------------------------------------------------------


def test_sim_implements_protocols() -> None:
    w = SimWorld()
    assert isinstance(SimFlightController(w), FlightController)
    assert isinstance(SimSLAM(w), SLAMProvider)
    assert isinstance(SimCamera(w), Camera)
    assert isinstance(SimLinkMonitor(w.now_ns), LinkMonitor)


# ---------------------------------------------------------------------------
# Flight controller state machine
# ---------------------------------------------------------------------------


def test_full_lifecycle_transitions() -> None:
    fc = SimFlightController(SimWorld())
    transitions: list[StateChange] = []
    fc.subscribe_state(transitions.append)

    fc.arm()
    fc.takeoff(1.5)
    fc.goto(3.0, 1.5, 1.0, 0.0)
    fc.land()

    sequence = [(t.from_state, t.to_state) for t in transitions]
    assert sequence == [
        (ControllerState.DISARMED, ControllerState.ARMED),
        (ControllerState.ARMED, ControllerState.AIRBORNE),
        (ControllerState.AIRBORNE, ControllerState.LANDING),
        (ControllerState.LANDING, ControllerState.DISARMED),
    ]


def test_goto_requires_airborne() -> None:
    fc = SimFlightController(SimWorld())
    fc.arm()
    with pytest.raises(RuntimeError, match="goto requires AIRBORNE"):
        fc.goto(1.0, 1.0, 1.0, 0.0)


def test_disarm_refuses_while_airborne() -> None:
    fc = SimFlightController(SimWorld())
    fc.arm()
    fc.takeoff(1.5)
    with pytest.raises(RuntimeError, match="cannot disarm while AIRBORNE"):
        fc.disarm()


def test_force_safe_hover_exposes_isc12_hook() -> None:
    fc = SimFlightController(SimWorld())
    fc.arm()
    fc.takeoff(1.5)
    transitions: list[StateChange] = []
    fc.subscribe_state(transitions.append)
    fc.force_safe_hover(reason="SLAM lost track")
    assert fc.get_state() is ControllerState.SAFE_HOVER
    assert transitions[-1].to_state is ControllerState.SAFE_HOVER
    assert transitions[-1].reason == "SLAM lost track"


# ---------------------------------------------------------------------------
# Telemetry bus
# ---------------------------------------------------------------------------


def test_bus_publishes_state_changes_when_wired() -> None:
    bus = InMemoryTelemetryBus()
    events: list[dict[str, object]] = []
    bus.subscribe("flight_control.state", lambda e: events.append(dict(e)))

    fc = SimFlightController(SimWorld(), bus=bus)
    fc.arm()
    fc.takeoff(1.5)

    assert len(events) == 2
    assert events[0]["payload"] == {
        "from": "disarmed",
        "to": "armed",
        "reason": "arm()",
    }


def test_bus_multiple_subscribers_per_topic() -> None:
    bus = InMemoryTelemetryBus()
    a: list[object] = []
    b: list[object] = []
    bus.subscribe("t", a.append)
    bus.subscribe("t", b.append)
    bus.publish("t", {"topic": "t", "timestamp_ns": 0, "payload": {}})
    assert len(a) == len(b) == 1


# ---------------------------------------------------------------------------
# SLAM
# ---------------------------------------------------------------------------


def test_slam_tracks_world_pose() -> None:
    world = SimWorld()
    slam = SimSLAM(world)
    slam.start()
    world.set_pose(2.0, 3.0, 1.0, 90.0)
    p = slam.get_pose()
    assert (p.x, p.y, p.z, p.yaw_deg) == (2.0, 3.0, 1.0, 90.0)


def test_slam_get_pose_before_start_raises() -> None:
    slam = SimSLAM(SimWorld())
    with pytest.raises(RuntimeError, match="before start"):
        slam.get_pose()


def test_slam_confidence_bounds() -> None:
    slam = SimSLAM(SimWorld())
    with pytest.raises(ValueError, match=r"\[0,1\]"):
        slam.set_confidence(1.5)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


def test_camera_deterministic_for_identical_pose() -> None:
    cam = SimCamera(SimWorld())
    cam.start()
    pose = Pose(1.0, 2.0, 1.5, 0.0, timestamp_ns=42)
    f1 = cam.capture(pose)
    f2 = cam.capture(pose)
    assert f1.pixels == f2.pixels
    assert f1.focus_score == f2.focus_score


def test_camera_distinct_poses_yield_distinct_frames() -> None:
    cam = SimCamera(SimWorld())
    cam.start()
    a = cam.capture(Pose(1.0, 2.0, 1.5, 0.0, timestamp_ns=0))
    b = cam.capture(Pose(1.0, 2.0, 1.5, 90.0, timestamp_ns=0))
    assert a.pixels != b.pixels


# ---------------------------------------------------------------------------
# Laplacian focus score
# ---------------------------------------------------------------------------


def test_focus_score_uniform_image_is_zero() -> None:
    flat = [128] * 25  # 5x5 uniform grey
    assert laplacian_focus_score(flat, 5, 5) == 0.0


def test_focus_score_step_function_is_positive() -> None:
    # Half black, half white — strong edge, nonzero Laplacian variance.
    pixels = [0] * 12 + [255] * 13  # 5x5 stepped at row 2
    assert laplacian_focus_score(pixels, 5, 5) > 0.0


def test_focus_score_rejects_mismatched_buffer() -> None:
    with pytest.raises(ValueError, match="length"):
        laplacian_focus_score([0, 1, 2], 5, 5)


def test_focus_score_rejects_tiny_image() -> None:
    with pytest.raises(ValueError, match="3x3"):
        laplacian_focus_score([0, 1, 2, 3], 2, 2)
