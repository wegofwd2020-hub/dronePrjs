"""ISC-12 SlamWatchdog — mid-mission SLAM loss → ``SAFE_HOVER``.

:class:`SlamWatchdog` owns the ``AIRBORNE → SAFE_HOVER`` trigger. The
mission runner calls :meth:`poll` once per loop iteration (its own
cadence is the poll interval); this class performs no I/O, no sleeps,
and must be single-threaded.

Transition rules (see ISC-12 plan §2):
* Only fires from ``AIRBORNE``; ground states are never touched.
* Guard is strict ``<`` against the threshold — exactly-at-threshold
  still counts as tracking.
* Idempotent: a second poll while already ``SAFE_HOVER`` fires nothing.
* If :meth:`SLAMProvider.confidence` raises, treat it as loss — unknown
  tracking is unsafe, so we still transition.
"""
from __future__ import annotations

import time
from typing import Callable

from closedSpace.constants import (
    SAFE_HOVER_MAX_LATENCY_S,
    SLAM_CONFIDENCE_THRESHOLD,
    SLAM_POLL_INTERVAL_S,
)
from engine.flight_control import ControllerState, FlightController
from engine.localization import SLAMProvider

__all__ = ["SlamWatchdog"]


class SlamWatchdog:
    """Polls SLAM tracking confidence; drops the controller to ``SAFE_HOVER``."""

    def __init__(
        self,
        slam: SLAMProvider,
        fc: FlightController,
        *,
        threshold: float = SLAM_CONFIDENCE_THRESHOLD,
        poll_interval_s: float = SLAM_POLL_INTERVAL_S,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._slam = slam
        self._fc = fc
        self._threshold = threshold
        self._poll_interval_s = poll_interval_s
        if poll_interval_s > SAFE_HOVER_MAX_LATENCY_S:
            raise ValueError(
                f"poll_interval_s={poll_interval_s} exceeds latency budget "
                f"SAFE_HOVER_MAX_LATENCY_S={SAFE_HOVER_MAX_LATENCY_S}"
            )
        self._clock = clock or time.monotonic_ns
        #: monotonic ns stamp of the first observed loss (None until one).
        self.first_loss_ns: int | None = None
        #: Reason string most recently used to command ``SAFE_HOVER``.
        self.last_reason: str = ""

    @property
    def threshold(self) -> float:
        """Confidence below which tracking is considered lost."""
        return self._threshold

    @property
    def poll_interval_s(self) -> float:
        """Runner's expected call cadence (s); kept for post-hoc audit."""
        return self._poll_interval_s

    def poll(self) -> bool:
        """Check confidence once. Return True iff ``SAFE_HOVER`` transition fired."""
        state = self._fc.get_state()
        if state is ControllerState.SAFE_HOVER:
            # Already in the safety state — idempotent, no new event.
            return False
        if state is not ControllerState.AIRBORNE:
            # Ground / landing: nothing to protect, never transition.
            return False
        confidence = self._confidence_or_loss()
        if confidence >= self._threshold:
            return False
        now = self._clock()
        if self.first_loss_ns is None:
            self.first_loss_ns = now
        self.last_reason = f"slam confidence {confidence:.3f} < {self._threshold}"
        self._fc.request_safe_hover(self.last_reason)
        return True

    def _confidence_or_loss(self) -> float:
        """SLAM confidence, or 0.0 if the provider raises (unknown = unsafe)."""
        try:
            return float(self._slam.confidence())
        except Exception:  # noqa: BLE001 — any provider failure means untracked
            self.last_reason = "slam confidence() raised — treating as loss"
            return 0.0