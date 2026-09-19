"""ISC-15 LinkLossWatchdog — ground-station link loss → RTH + land.

:class:`LinkLossWatchdog` owns the ``AIRBORNE → goto(home) → land`` and
``SAFE_HOVER → land`` triggers. The mission runner calls :meth:`poll`
once per loop iteration (its own cadence is the poll interval); this
class performs no I/O, no sleeps, and must be single-threaded.

Transition rules (see ISC-15 plan §2):
* Only acts from ``AIRBORNE`` or ``SAFE_HOVER``; ground / landing states
  are never touched.
* Guard is strict ``>`` against the timeout — exactly-at-timeout still
  counts as connected.
* From ``AIRBORNE``: ``goto(home)`` then ``land()`` (return-to-home).
* From ``SAFE_HOVER``: ``land()`` directly — ``goto()`` raises there.
* If :meth:`LinkMonitor.last_heartbeat_ns` raises, treat elapsed as
  maximum (unknown = unsafe) → trigger.
* A never-heartbeated link (``last_heartbeat_ns()`` low / 0) yields an
  elapsed delta ``now - 0`` that exceeds the timeout on the first
  airborne poll — the guard is purely the elapsed delta.
"""
from __future__ import annotations

import time
from typing import Callable

from closedSpace.constants import LINK_LOSS_TIMEOUT_S, LINK_POLL_INTERVAL_S
from engine.flight_control import ControllerState, FlightController
from engine.link import LinkMonitor
from engine.types import Pose

__all__ = ["LinkLossWatchdog"]


class LinkLossWatchdog:
    """Polls keepalive age; triggers return-to-home + land on link loss."""

    def __init__(
        self,
        link: LinkMonitor,
        fc: FlightController,
        home: Pose,
        *,
        timeout_s: float = LINK_LOSS_TIMEOUT_S,
        poll_interval_s: float = LINK_POLL_INTERVAL_S,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._link = link
        self._fc = fc
        self._home = home
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        if poll_interval_s > timeout_s / 2:
            raise ValueError(
                f"poll_interval_s={poll_interval_s} exceeds timeout_s/2={timeout_s / 2} "
                "— at least two polls must fit inside the timeout window"
            )
        self._clock = clock or time.monotonic_ns
        #: monotonic ns stamp of the first observed loss (None until one).
        self.first_loss_ns: int | None = None
        #: Reason string most recently used to justify a trigger.
        self.last_reason: str = ""

    @property
    def timeout_s(self) -> float:
        """Silence beyond which the link counts as lost."""
        return self._timeout_s

    @property
    def poll_interval_s(self) -> float:
        """Runner's expected call cadence (s); kept for post-hoc audit."""
        return self._poll_interval_s

    def poll(self) -> bool:
        """Check link age once. Return True iff RTH+land was triggered."""
        state = self._fc.get_state()
        if state not in (ControllerState.AIRBORNE, ControllerState.SAFE_HOVER):
            # Ground / already landing: nothing to protect, never act.
            return False
        now = self._clock()
        last = self._last_heartbeat_or_unknown()
        if last is None:
            # Link provider failed — unknown contact, act now.
            elapsed_ns = now
            lost = True
        else:
            elapsed_ns = now - last
            lost = elapsed_ns > self._timeout_ns()
        if not lost:
            return False
        if self.first_loss_ns is None:
            self.first_loss_ns = now
        self.last_reason = (
            f"link silent for {elapsed_ns / 1_000_000_000:.3f}s > "
            f"{self._timeout_s}s"
        )
        if state is ControllerState.AIRBORNE:
            self._fc.goto(
                self._home.x, self._home.y, self._home.z, self._home.yaw_deg
            )
        # SAFE_HOVER: goto() raises there — land directly, drone is parked.
        self._fc.land()
        return True

    def _timeout_ns(self) -> int:
        return int(self._timeout_s * 1_000_000_000)

    def _last_heartbeat_or_unknown(self) -> int | None:
        """Provider's last heartbeat, or None if it raises (unknown = unsafe).
        A monotonic 0 is *not* treated specially: since the clock source
        could legitimately start at 0, only the elapsed delta matters."""
        try:
            return int(self._link.last_heartbeat_ns())
        except Exception:  # noqa: BLE001 — any provider failure means unknown contact
            self.last_reason = "link.last_heartbeat_ns() raised — treating as loss"
            return None