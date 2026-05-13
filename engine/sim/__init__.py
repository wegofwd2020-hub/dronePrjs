"""engine.sim — in-process kinematic stubs for every engine Protocol.

These stubs let closedSpace (and openSpace) run a planned mission
end-to-end without real hardware. They're deliberately simple:

* :class:`SimWorld` — single source of truth for the simulated pose and
  monotonic clock. Both SLAM and Camera read from it; FlightController
  writes to it.
* :class:`SimFlightController` — implements the flight state machine;
  ``goto`` snaps the world pose instantly (no kinematics, no time
  integration). Publishes state changes if a bus is wired in.
* :class:`SimSLAM` — reads the world pose. ``confidence()`` is 1.0
  unless explicitly degraded via :meth:`SimSLAM.set_confidence`, the
  hook ISC-12's loss-of-tracking probe uses.
* :class:`SimCamera` — emits a small deterministic grayscale frame
  derived from the current pose, plus the real Laplacian focus score
  for it. Same pose → same bytes (lets tests assert determinism).

Suitability gate: this sim is for unit + smoke testing. Anything that
needs sensor fidelity (real SLAM drift, motion blur, lighting) must use
the Phase 3 simulator behind the same Protocols.
"""
from __future__ import annotations

import hashlib
import itertools
import time
from typing import Callable

from engine.flight_control import (
    ControllerState,
    FlightController,
    StateCallback,
    StateChange,
)
from engine.localization import SLAMProvider
from engine.sensors import Camera, Frame, laplacian_focus_score
from engine.telemetry import TelemetryBus
from engine.types import Pose

#: Default field size for synthetic frames. Small enough that the
#: stdlib Laplacian loop stays fast; large enough that the focus score
#: has meaningful variance.
_FRAME_W: int = 16
_FRAME_H: int = 16


class SimWorld:
    """The simulated environment's shared mutable state.

    Holds the current pose and a monotonic timestamp source. The
    FlightController is the only writer; SLAM and Camera are readers.
    A single instance is shared across all Sim* objects in one mission.
    """

    def __init__(
        self, initial_pose: Pose | None = None, clock: Callable[[], int] | None = None
    ) -> None:
        self._clock = clock or time.monotonic_ns
        self._pose = initial_pose or Pose(0.0, 0.0, 0.0, 0.0, self._clock())

    @property
    def pose(self) -> Pose:
        return self._pose

    def set_pose(self, x: float, y: float, z: float, yaw_deg: float) -> Pose:
        self._pose = Pose(x, y, z, yaw_deg, self._clock())
        return self._pose

    def now_ns(self) -> int:
        return self._clock()


class SimFlightController:
    """In-process :class:`FlightController` with instant-snap kinematics.

    State transitions are enforced by :meth:`_transition`. Illegal
    requests (e.g. ``goto`` while DISARMED) raise ``RuntimeError`` to
    surface mission-runner bugs early rather than silently no-op'ing.
    """

    def __init__(
        self, world: SimWorld, bus: TelemetryBus | None = None
    ) -> None:
        self._world = world
        self._bus = bus
        self._state = ControllerState.DISARMED
        self._subs: list[StateCallback] = []

    def arm(self) -> None:
        if self._state is ControllerState.ARMED:
            return
        self._transition(ControllerState.ARMED, reason="arm()")

    def disarm(self) -> None:
        if self._state is ControllerState.AIRBORNE:
            raise RuntimeError("cannot disarm while AIRBORNE — land first")
        if self._state is ControllerState.DISARMED:
            return
        self._transition(ControllerState.DISARMED, reason="disarm()")

    def takeoff(self, height_m: float) -> None:
        if self._state is not ControllerState.ARMED:
            raise RuntimeError(
                f"takeoff requires ARMED; current state is {self._state.value}"
            )
        p = self._world.pose
        self._world.set_pose(p.x, p.y, height_m, p.yaw_deg)
        self._transition(ControllerState.AIRBORNE, reason=f"takeoff({height_m})")

    def land(self) -> None:
        if self._state is not ControllerState.AIRBORNE:
            raise RuntimeError(
                f"land requires AIRBORNE; current state is {self._state.value}"
            )
        self._transition(ControllerState.LANDING, reason="land()")
        p = self._world.pose
        self._world.set_pose(p.x, p.y, 0.0, p.yaw_deg)
        self._transition(ControllerState.DISARMED, reason="land() complete")

    def goto(self, x: float, y: float, z: float, yaw_deg: float) -> None:
        if self._state is not ControllerState.AIRBORNE:
            raise RuntimeError(
                f"goto requires AIRBORNE; current state is {self._state.value}"
            )
        self._world.set_pose(x, y, z, yaw_deg)

    def hold(self) -> None:
        # Snap-kinematic sim has nothing to integrate; hold is a no-op.
        return

    def get_state(self) -> ControllerState:
        return self._state

    def get_pose(self) -> Pose:
        return self._world.pose

    def subscribe_state(self, cb: StateCallback) -> None:
        self._subs.append(cb)

    def force_safe_hover(self, reason: str) -> None:
        """Hook for ISC-12 probes: external trigger of the safety state."""
        if self._state is ControllerState.SAFE_HOVER:
            return
        self._transition(ControllerState.SAFE_HOVER, reason=reason)

    def _transition(self, to: ControllerState, *, reason: str) -> None:
        change = StateChange(
            from_state=self._state,
            to_state=to,
            timestamp_ns=self._world.now_ns(),
            reason=reason,
        )
        self._state = to
        for cb in self._subs:
            cb(change)
        if self._bus is not None:
            self._bus.publish(
                "flight_control.state",
                {
                    "topic": "flight_control.state",
                    "timestamp_ns": change.timestamp_ns,
                    "payload": {
                        "from": change.from_state.value,
                        "to": change.to_state.value,
                        "reason": change.reason,
                    },
                },
            )


class SimSLAM:
    """In-process :class:`SLAMProvider` — mirrors the world pose."""

    def __init__(self, world: SimWorld) -> None:
        self._world = world
        self._started = False
        self._confidence = 1.0

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_pose(self) -> Pose:
        if not self._started:
            raise RuntimeError("SimSLAM.get_pose called before start()")
        return self._world.pose

    def confidence(self) -> float:
        return self._confidence

    def set_confidence(self, value: float) -> None:
        """Test hook: degrade tracking confidence to exercise ISC-12."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence must be in [0,1]; got {value}")
        self._confidence = value


class SimCamera:
    """In-process :class:`Camera`.

    Produces a deterministic ``_FRAME_W × _FRAME_H`` grayscale frame
    keyed off a SHA-256 of the pose tuple — so identical poses yield
    identical bytes (useful for byte-stable tests). The focus score is
    the real Laplacian variance of those bytes.
    """

    def __init__(self, world: SimWorld) -> None:
        self._world = world
        self._started = False
        self._capture_seq = itertools.count(1)

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def capture(self, pose: Pose) -> Frame:
        if not self._started:
            raise RuntimeError("SimCamera.capture called before start()")
        pixels = _synthetic_frame(pose)
        score = laplacian_focus_score(pixels, _FRAME_W, _FRAME_H)
        next(self._capture_seq)
        return Frame(
            pixels=bytes(pixels),
            width=_FRAME_W,
            height=_FRAME_H,
            pose=pose,
            focus_score=score,
        )


def _synthetic_frame(pose: Pose) -> list[int]:
    """Deterministic grayscale pattern keyed off the pose tuple."""
    seed = hashlib.sha256(
        f"{pose.x:.6f},{pose.y:.6f},{pose.z:.6f},{pose.yaw_deg:.6f}".encode()
    ).digest()
    # Tile the 32-byte digest across the frame; XOR with (x+y) to give
    # the buffer some structure (so the Laplacian variance is nonzero).
    out: list[int] = []
    for y in range(_FRAME_H):
        for x in range(_FRAME_W):
            idx = (y * _FRAME_W + x) % len(seed)
            out.append((seed[idx] ^ (x * 7 + y * 13)) & 0xFF)
    return out


# Conformance: assert structural subtyping at import time so test discovery
# fails loudly if a Protocol method gets renamed.
_: tuple[
    type[SLAMProvider], type[FlightController], type[Camera]
] = (SimSLAM, SimFlightController, SimCamera)


__all__ = [
    "SimCamera",
    "SimFlightController",
    "SimSLAM",
    "SimWorld",
]
