"""ISC-14 ClearanceWatchdog — per-waypoint clearance enforcement.

:class:`ClearanceWatchdog` polls a :class:`ProximitySensor` after every
``_execute()`` call and:

* Always publishes a ``control.clearance`` telemetry event with the
  measured ``min_clearance_m`` (used by the post-flight log scan).
* On violation (< MIN_CLEARANCE_M): publishes a ``control.collision``
  event with ``severity: "COLLISION"`` and transitions to ``SAFE_HOVER``.

Geofence rule (ISC-33): only checks clearance when
``fc.get_state() is AIRBORNE`` AND ``fc.get_pose().z >=
CLEARANCE_GEOFENCE_HEIGHT_M``. This exempts the takeoff climb and
landing descent where the drone is legitimately close to the floor.

Single-threaded, synchronous — driven by the mission runner loop.
"""
from __future__ import annotations

import time
from typing import Callable

from closedSpace.constants import CLEARANCE_GEOFENCE_HEIGHT_M, MIN_CLEARANCE_M
from engine.flight_control import ControllerState, FlightController
from engine.sensors import ProximitySensor
from engine.telemetry import TelemetryBus

__all__ = ["ClearanceWatchdog"]


class ClearanceWatchdog:
    """Polls proximity sensor; logs clearance telemetry; fires on violation."""

    def __init__(
        self,
        sensor: ProximitySensor,
        fc: FlightController,
        *,
        geofence_height_m: float = CLEARANCE_GEOFENCE_HEIGHT_M,
        bus: TelemetryBus | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._sensor = sensor
        self._fc = fc
        self._geofence_height_m = geofence_height_m
        self._bus = bus
        self._clock = clock or time.monotonic_ns
        #: Monotonic ns of the first clearance violation, or None.
        self.first_violation_ns: int | None = None
        #: Reason string from the most recent violation (empty until one).
        self.last_reason: str = ""

    def poll(self) -> bool:
        """Check clearance once. Log event. Return True iff SAFE_HOVER fired.

        Returns:
            True if a violation was detected and the controller was
            transitioned to SAFE_HOVER. False in all other cases.

        Raises:
            Nothing. Sensor exceptions are caught and treated as violations.
        """
        state = self._fc.get_state()
        if state is not ControllerState.AIRBORNE:
            return False
        pose = self._fc.get_pose()
        if pose.z < self._geofence_height_m:
            return False

        clearance = self._clearance_or_violation()
        violation = clearance < MIN_CLEARANCE_M

        self._publish_clearance(clearance, violation=violation)

        if not violation:
            return False

        reason = f"clearance {clearance:.3f} m < MIN_CLEARANCE_M {MIN_CLEARANCE_M}"
        self.last_reason = reason
        if self.first_violation_ns is None:
            self.first_violation_ns = self._clock()

        self._publish_collision(clearance, reason)
        self._fc.request_safe_hover(reason)
        return True

    # ------------------------------------------------------------------

    def _clearance_or_violation(self) -> float:
        """Sensor reading, or 0.0 if it raises (unknown clearance = unsafe)."""
        try:
            return float(self._sensor.min_clearance_m())
        except Exception:  # noqa: BLE001 — any sensor failure means unknown
            self.last_reason = "proximity sensor raised — treating as violation"
            return 0.0

    def _publish_clearance(self, clearance_m: float, *, violation: bool) -> None:
        """Publish one control.clearance sample to the telemetry bus."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.clearance",
            {
                "topic": "control.clearance",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "violation": violation,
                },
            },
        )

    def _publish_collision(self, clearance_m: float, reason: str) -> None:
        """Publish a control.collision event with severity COLLISION."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.collision",
            {
                "topic": "control.collision",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "severity": "COLLISION",
                    "reason": reason,
                },
            },
        )
