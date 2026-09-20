"""closedSpace.control — safety-critical flight-time control.

* :class:`SlamWatchdog` — ISC-12 loss-of-tracking detector. Polls SLAM
  confidence while airborne and drops the controller to ``SAFE_HOVER``
  within the mission latency budget.
* :class:`LinkLossWatchdog` — ISC-15 ground-station link-loss detector.
  On keepalive silence beyond the timeout it triggers return-to-home +
  land (or a direct land from ``SAFE_HOVER``).
* :class:`LatencyRecorder` — ISC-13 per-waypoint perception-to-command
  latency recorder. Driven synchronously by the mission runner loop;
  exposes p99 in both ns and s for soak-test assertions.

Public surface is intentionally small: two watchdogs + one recorder,
all driven synchronously by the mission runner's loop.
"""
from __future__ import annotations

from closedSpace.control.latency import LatencyRecorder
from closedSpace.control.link_watchdog import LinkLossWatchdog
from closedSpace.control.watchdog import SlamWatchdog

__all__ = ["LatencyRecorder", "LinkLossWatchdog", "SlamWatchdog"]