"""engine.flight_control — flight-stack-agnostic command surface.

The :class:`FlightController` Protocol is the only point of contact
between the mission layer and whatever drone stack actually flies the
airframe (PX4, ArduPilot, a vendor SDK, or the in-process sim). Choice
of stack is open decision D3 in ``docs/next-steps.md``.

State semantics
---------------

The controller is a small state machine. Lifecycle transitions go:

    DISARMED → ARMED → AIRBORNE → ARMED → DISARMED
                       ↓
                  SAFE_HOVER (ISC-12) on SLAM loss / link loss

``SAFE_HOVER`` is a self-loop; only the host can recover from it. Every
state change emits a :class:`StateChange` event to subscribers — the
mission runner uses this to gate progression and the telemetry bus
logs it for ISC-29's 1 Hz log.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

from engine.types import Pose


class ControllerState(Enum):
    """The five operational states a controller can be in."""

    DISARMED = "disarmed"
    ARMED = "armed"
    AIRBORNE = "airborne"
    SAFE_HOVER = "safe_hover"
    LANDING = "landing"


@dataclass(frozen=True, slots=True)
class StateChange:
    """One transition between :class:`ControllerState` values."""

    from_state: ControllerState
    to_state: ControllerState
    timestamp_ns: int
    reason: str


#: Callback signature for state-change subscribers. The runner registers
#: one of these via :meth:`FlightController.subscribe_state`.
StateCallback = Callable[[StateChange], None]


@runtime_checkable
class FlightController(Protocol):
    """The cross-stack flight-command surface.

    All methods are synchronous; concrete stacks may run async I/O under
    the hood, but the surface here blocks until the commanded transition
    is acknowledged (or the controller has dropped to ``SAFE_HOVER``,
    in which case the caller observes the state change via subscription
    and decides whether to abort).
    """

    def arm(self) -> None:
        """Transition DISARMED → ARMED. Idempotent on ARMED."""
        ...

    def disarm(self) -> None:
        """Transition any non-AIRBORNE state → DISARMED. Refuses while AIRBORNE."""
        ...

    def takeoff(self, height_m: float) -> None:
        """ARMED → AIRBORNE at the given hover height above the pad."""
        ...

    def land(self) -> None:
        """AIRBORNE → LANDING → DISARMED at the current XY."""
        ...

    def request_safe_hover(self, reason: str) -> None:
        """Drop to ``SAFE_HOVER``, e.g. on SLAM/link loss (ISC-12).

        Idempotent while already ``SAFE_HOVER`` — no second event fires.
        Mid-mission gating (only transition from ``AIRBORNE``) is the
        caller's job: the SLAM watchdog checks state before invoking.
        """
        ...

    def goto(self, x: float, y: float, z: float, yaw_deg: float) -> None:
        """Command a waypoint; returns when the airframe is within
        the platform's per-axis arrival tolerance.
        """
        ...

    def hold(self) -> None:
        """Latch current pose. Used between captures during dwell."""
        ...

    def get_state(self) -> ControllerState:
        """Current controller state. Non-blocking."""
        ...

    def get_pose(self) -> Pose:
        """Latest known commanded pose. Non-blocking."""
        ...

    def subscribe_state(self, cb: StateCallback) -> None:
        """Register a callback fired on every state transition."""
        ...


__all__ = [
    "ControllerState",
    "FlightController",
    "StateCallback",
    "StateChange",
]
