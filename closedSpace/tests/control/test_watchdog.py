"""Tests for :class:`closedSpace.control.SlamWatchdog`.

Covers the seven ISC-12 assertions: transition fires on loss, latency
within the 200 ms budget, event published, no ground transition, exact
threshold boundary, idempotent second poll, and confidence() raising
still transitions.
"""
from __future__ import annotations

import pytest

from closedSpace.constants import (
    SAFE_HOVER_MAX_LATENCY_S,
    SLAM_CONFIDENCE_THRESHOLD,
)
from closedSpace.control import SlamWatchdog
from engine.flight_control import ControllerState, StateChange
from engine.sim import SimFlightController, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus


class _FakeClock:
    """Manual monotonic-ns clock; advance() lets tests control time."""

    def __init__(self, start_ns: int = 0) -> None:
        self._t = start_ns

    def advance(self, ns: int) -> None:
        self._t += ns

    def __call__(self) -> int:
        return self._t


def _make_watchdog(bus: InMemoryTelemetryBus | None = None):
    """Wire a watchdog without any ground / altitude progress, fully synced."""
    clock = _FakeClock()
    world = SimWorld(clock=clock)
    fc = SimFlightController(world, bus=bus)
    slam = SimSLAM(world)
    return clock, fc, slam


def _airborne(fc: SimFlightController) -> None:
    fc.arm()
    fc.takeoff(1.0)


# ---------------------------------------------------------------------------
# 1. Transition fires — confidence < threshold while AIRBORNE → SAFE_HOVER
# ---------------------------------------------------------------------------


def test_low_confidence_fires_safe_hover() -> None:
    clock, fc, slam = _make_watchdog()
    _airborne(fc)
    slam.set_confidence(0.1)
    watchdog = SlamWatchdog(slam=slam, fc=fc, clock=clock)

    assert watchdog.poll()
    assert fc.get_state() is ControllerState.SAFE_HOVER
    assert watchdog.first_loss_ns is not None


# ---------------------------------------------------------------------------
# 2. Latency budget — loss-to-StateChange delta ≤ 200 ms
# ---------------------------------------------------------------------------


def test_loss_to_transition_latency_within_budget() -> None:
    clock, fc, slam = _make_watchdog()
    _airborne(fc)
    slam.set_confidence(0.1)
    changes: list[StateChange] = []
    fc.subscribe_state(changes.append)

    watchdog = SlamWatchdog(slam=slam, fc=fc, clock=clock)
    clock.advance(5_000_000)  # 5 ms of flight before the loss presents
    assert watchdog.poll()
    safe_hover = next(c for c in changes if c.to_state is ControllerState.SAFE_HOVER)

    assert watchdog.first_loss_ns is not None
    latency_ns = safe_hover.timestamp_ns - watchdog.first_loss_ns
    budget_ns = int(SAFE_HOVER_MAX_LATENCY_S * 1_000_000_000)
    assert 0 <= latency_ns <= budget_ns


# ---------------------------------------------------------------------------
# 3. State-change event logged with timestamp_ns
# ---------------------------------------------------------------------------


def test_state_change_event_published_with_timestamp() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, slam = _make_watchdog(bus=bus)
    _airborne(fc)
    slam.set_confidence(0.05)
    events: list[dict] = []
    bus.subscribe("flight_control.state", events.append)

    SlamWatchdog(slam=slam, fc=fc, clock=clock).poll()

    last = events[-1]
    assert last["topic"] == "flight_control.state"
    assert last["timestamp_ns"] == clock()
    assert last["payload"]["to"] == "safe_hover"


# ---------------------------------------------------------------------------
# 4. No ground transition — DISARMED / ARMED + low confidence → no-op
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "grounded", [ControllerState.DISARMED, ControllerState.ARMED]
)
def test_no_transition_from_ground_states(grounded: ControllerState) -> None:
    clock, fc, slam = _make_watchdog()
    if grounded is ControllerState.ARMED:
        fc.arm()
    slam.set_confidence(0.05)

    watchdog = SlamWatchdog(slam=slam, fc=fc, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is grounded


# ---------------------------------------------------------------------------
# 5. Strict boundary — confidence exactly == threshold → no transition
# ---------------------------------------------------------------------------


def test_exact_threshold_does_not_transition() -> None:
    clock, fc, slam = _make_watchdog()
    _airborne(fc)
    slam.set_confidence(SLAM_CONFIDENCE_THRESHOLD)

    watchdog = SlamWatchdog(slam=slam, fc=fc, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE


# ---------------------------------------------------------------------------
# 6. Idempotency — second poll while SAFE_HOVER fires no event
# ---------------------------------------------------------------------------


def test_second_poll_is_idempotent() -> None:
    clock, fc, slam = _make_watchdog()
    _airborne(fc)
    slam.set_confidence(0.05)
    changes: list[StateChange] = []
    fc.subscribe_state(changes.append)

    watchdog = SlamWatchdog(slam=slam, fc=fc, clock=clock)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.SAFE_HOVER
    count_after_first = len(changes)

    assert not watchdog.poll()
    assert len(changes) == count_after_first
    assert fc.get_state() is ControllerState.SAFE_HOVER


# ---------------------------------------------------------------------------
# 7. confidence() raises → treated as loss, still transitions
# ---------------------------------------------------------------------------


class _RaisingSlam(SimSLAM):
    def confidence(self) -> float:
        raise RuntimeError("tracker crashed")


def test_confidence_exception_still_transitions() -> None:
    world = SimWorld()
    fc = SimFlightController(world)
    slam = _RaisingSlam(world)
    _airborne(fc)

    watchdog = SlamWatchdog(slam=slam, fc=fc)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.SAFE_HOVER