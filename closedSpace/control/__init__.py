"""closedSpace.control — safety-critical flight-time control.

* :class:`SlamWatchdog` — ISC-12 loss-of-tracking detector. Polls SLAM
  confidence while airborne and drops the controller to ``SAFE_HOVER``
  within the mission latency budget.

Public surface is intentionally small: one watchdog, driven synchronously
by the mission runner's loop.
"""
from __future__ import annotations

from closedSpace.control.watchdog import SlamWatchdog

__all__ = ["SlamWatchdog"]