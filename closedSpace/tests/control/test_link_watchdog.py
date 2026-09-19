"""Tests for :class:`closedSpace.control.LinkLossWatchdog`.

Covers the eight ISC-15 assertions: RTH fires on link loss from AIRBORNE,
active link stays put, ground states never act, strict timeout boundary,
SAFE_HOVER lands directly (no goto), event published with timestamp,
first_loss_ns recorded, and idempotency after landing. Plus the plan's
edge case: last_heartbeat_ns() raising still triggers.
"""
from __future__ import annotations

import pytest

from closedSpace.constants import LINK_LOSS_TIMEOUT_S
from closedSpace.control import LinkLossWatchdog
from engine.flight_control import ControllerState, StateChange
from engine.sim import SimFlightController, SimLinkMonitor, SimWorld
from engine.telemetry import InMemoryTelemetryBus
from engine.types import Pose

HOME = Pose(x=1.0, y=2.0, z=1.0, yaw_deg=0.0, timestamp_ns=0)


class _FakeClock:
    """Manual monotonic-ns clock; advance() lets tests control time."""

    def __init__(self, start_ns: int = 0) -> None:
        self._t = start_ns

    def advance(self, ns: int) -> None:
        self._t += ns

    def __call__(self) -> int:
        return self._t


def _make_watchdog(bus: InMemoryTelemetryBus | None = None):
    """Wire a watchdog fully synced to one fake clock."""
    clock = _FakeClock()
    world = SimWorld(clock=clock)
    fc = SimFlightController(world, bus=bus)
    link = SimLinkMonitor(clock=clock)
    return clock, fc, link, HOME


def _airborne(fc: SimFlightController) -> None:
    fc.arm()
    fc.takeoff(1.0)


def _timeout_ns() -> int:
    return int(LINK_LOSS_TIMEOUT_S * 1_000_000_000)


def _beyond_timeout(clock: _FakeClock) -> None:
    clock.advance(_timeout_ns() + 1)


# ---------------------------------------------------------------------------
# 1. RTH fires — AIRBORNE + silence > timeout → goto(home) then land
# ---------------------------------------------------------------------------


def test_rth_fires_from_airborne_returns_home_and_lands() -> None:
    clock, fc, link, home = _make_watchdog()
    _airborne(fc)
    fc.goto(8.0, 8.0, 1.0, 0.0)  # fly away from the pad
    link.silence()
    _beyond_timeout(clock)
    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)

    assert watchdog.poll()
    assert fc.get_state() is ControllerState.DISARMED
    pose = fc.get_pose()
    assert pose.x == home.x and pose.y == home.y  # returned to the pad
    assert pose.z == 0.0  # descended
    assert "link" in watchdog.last_reason


# ---------------------------------------------------------------------------
# 2. Active link — heartbeats arriving → no RTH
# ---------------------------------------------------------------------------


def test_active_link_never_triggers() -> None:
    clock, fc, link, home = _make_watchdog()
    _airborne(fc)
    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)

    assert not watchdog.poll()
    clock.advance(2_000_000_000)  # 2 s of flight…
    link.heartbeat()  # …but the ground station keeps talking
    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE


# ---------------------------------------------------------------------------
# 3. No ground transition — DISARMED / ARMED + silence → no RTH
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grounded", [ControllerState.DISARMED, ControllerState.ARMED])
def test_no_action_from_ground_states(grounded: ControllerState) -> None:
    clock, fc, link, home = _make_watchdog()
    if grounded is ControllerState.ARMED:
        fc.arm()
    link.silence()
    _beyond_timeout(clock)

    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)
    assert not watchdog.poll()
    assert fc.get_state() is grounded


# ---------------------------------------------------------------------------
# 4. Strict boundary — elapsed exactly == timeout → no trigger
# ---------------------------------------------------------------------------


def test_exact_timeout_does_not_trigger() -> None:
    clock, fc, link, home = _make_watchdog()
    _airborne(fc)
    link.silence()
    clock.advance(_timeout_ns())  # exactly at the line — still "connected"
    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)

    assert not watchdog.poll()
    assert fc.get_state() is ControllerState.AIRBORNE

    clock.advance(1)  # one nanosecond later → lost
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.DISARMED


# ---------------------------------------------------------------------------
# 5. SAFE_HOVER + silence > timeout → land() directly, no goto()
# ---------------------------------------------------------------------------


def test_safe_hover_lands_directly_without_goto() -> None:
    clock, fc, link, _home = _make_watchdog()
    _airborne(fc)
    fc.goto(8.0, 8.0, 1.0, 0.0)  # away from home — a goto back would move us
    fc.force_safe_hover("test")
    link.silence()
    _beyond_timeout(clock)
    watchdog = LinkLossWatchdog(link=link, fc=fc, home=HOME, clock=clock)

    assert watchdog.poll()
    assert fc.get_state() is ControllerState.DISARMED
    pose = fc.get_pose()
    # x/y unchanged from the SAFE_HOVER position → landing was direct.
    assert pose.x == 8.0 and pose.y == 8.0
    assert pose.z == 0.0


# ---------------------------------------------------------------------------
# 6. Event logged — flight_control.state with timestamp_ns on trigger
# ---------------------------------------------------------------------------


def test_rth_publishes_state_event_with_timestamp() -> None:
    bus = InMemoryTelemetryBus()
    clock, fc, link, home = _make_watchdog(bus=bus)
    _airborne(fc)
    link.silence()
    _beyond_timeout(clock)
    events: list[dict] = []
    bus.subscribe("flight_control.state", events.append)

    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)
    assert watchdog.poll()

    assert any(e["topic"] == "flight_control.state" for e in events)
    entry = events[-1]
    assert entry["timestamp_ns"] == clock()
    assert entry["payload"]["to"] == "disarmed"


# ---------------------------------------------------------------------------
# 7. first_loss_ns recorded at the poll that detected the loss
# ---------------------------------------------------------------------------


def test_first_loss_ns_recorded_at_poll_time() -> None:
    clock, fc, link, home = _make_watchdog()
    _airborne(fc)
    link.silence()
    clock.advance(_timeout_ns() + 123_456_789)  # lost, well past the line
    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)

    assert watchdog.first_loss_ns is None
    assert watchdog.poll()
    assert watchdog.first_loss_ns == clock()


# ---------------------------------------------------------------------------
# 8. Idempotent — poll after landing (DISARMED) does nothing
# ---------------------------------------------------------------------------


def test_poll_after_landing_is_idempotent() -> None:
    clock, fc, link, home = _make_watchdog()
    _airborne(fc)
    link.silence()
    _beyond_timeout(clock)
    changes: list[StateChange] = []
    fc.subscribe_state(changes.append)

    watchdog = LinkLossWatchdog(link=link, fc=fc, home=home, clock=clock)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.DISARMED
    count_after_rth = len(changes)

    assert not watchdog.poll()
    assert len(changes) == count_after_rth
    assert fc.get_state() is ControllerState.DISARMED


# ---------------------------------------------------------------------------
# Edge (plan §7) — last_heartbeat_ns() raises → treat as loss, still RTH
# ---------------------------------------------------------------------------


class _RaisingLink(SimLinkMonitor):
    def last_heartbeat_ns(self) -> int:
        raise RuntimeError("link monitor crashed")


def test_heartbeat_exception_still_triggers() -> None:
    world = SimWorld()
    fc = SimFlightController(world)
    link = _RaisingLink(world.now_ns)
    _airborne(fc)

    watchdog = LinkLossWatchdog(link=link, fc=fc, home=HOME)
    assert watchdog.poll()
    assert fc.get_state() is ControllerState.DISARMED