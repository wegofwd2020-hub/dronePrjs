"""Mission runner — drives plan + sim + capture + storage + report.

Single entry point: :meth:`MissionRunner.run`. Wires every Phase 2–4
component together with two operator-facing concerns:

* **Abort polling.** Before every waypoint the runner checks an
  :class:`AbortSignal`. On abort during ``AIRBORNE`` it calls
  ``fc.land()`` immediately — the per-waypoint check is the v1 abort
  latency budget. For real hardware with long inter-waypoint dwells,
  Phase 8 will need to poll inside the dwell too.
* **Progress events.** The runner publishes one
  ``mission.progress`` event per waypoint and one ``mission.started``
  / ``mission.finished`` bracket — these are what
  :class:`engine.telemetry.JSONLTelemetryLogger` captures for the
  1 Hz log mandated by ISC-29.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from closedSpace.capture import CaptureSink
from closedSpace.control import SlamWatchdog
from closedSpace.mission import MissionPlan, Waypoint
from closedSpace.report import ReportBuilder
from engine.flight_control import ControllerState
from engine.sim import SimCamera, SimFlightController
from engine.telemetry import TelemetryBus


class AbortSignal:
    """Thread-safe one-shot abort flag.

    The CLI installs a stdin reader thread that calls
    :meth:`trigger`; tests trigger it programmatically.
    """

    def __init__(self) -> None:
        self._set = threading.Event()
        self._reason = ""

    def trigger(self, reason: str = "operator abort") -> None:
        """Latch the abort flag and record the reason. Safe from any thread."""
        self._reason = reason
        self._set.set()

    def is_set(self) -> bool:
        """True iff :meth:`trigger` has been called."""
        return self._set.is_set()

    @property
    def reason(self) -> str:
        """The reason string passed to the most recent :meth:`trigger` call."""
        return self._reason


@dataclass(frozen=True, slots=True)
class MissionRunResult:
    """What the runner returns to the CLI."""

    report: dict[str, Any]
    aborted: bool
    abort_reason: str


class MissionRunner:
    """Owns the per-waypoint drive loop.

    Construct one per mission; call :meth:`run` once. The caller is
    responsible for starting the SLAM/Camera (this runner doesn't
    own their lifecycle so the same Sim wiring can be re-used across
    tests).
    """

    def __init__(
        self,
        *,
        plan: MissionPlan,
        fc: SimFlightController,
        cam: SimCamera,
        sink: CaptureSink,
        builder: ReportBuilder,
        bus: TelemetryBus | None = None,
        abort_signal: AbortSignal | None = None,
        watchdog: SlamWatchdog | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._plan = plan
        self._fc = fc
        self._cam = cam
        self._sink = sink
        self._builder = builder
        self._bus = bus
        self._abort = abort_signal or AbortSignal()
        self._watchdog = watchdog
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Hook the controller's state stream into the report's
        # telemetry-summary counter without forcing every test to do it.
        fc.subscribe_state(lambda _ev: builder.record_state_transition())

    def run(self) -> MissionRunResult:
        """Drive every waypoint; return the finalized mission report."""
        self._publish_progress("mission.started", payload={
            "planned_capture_count": self._plan.capture_count,
            "planned_waypoints": len(self._plan.waypoints),
        })

        aborted = False
        abort_reason = ""
        for i, wp in enumerate(self._plan.waypoints):
            # ISC-12: watchdog is the highest-priority check — SLAM loss
            # preempts waypoint commands (and even an operator abort) so
            # the drone parks in SAFE_HOVER before anything else runs.
            if self._watchdog is not None and self._watchdog.poll():
                aborted = True
                abort_reason = self._watchdog.last_reason
                self._handle_abort()
                break
            if self._abort.is_set():
                aborted = True
                abort_reason = self._abort.reason
                self._handle_abort()
                break
            self._execute(wp, takeoff_height_m=self._plan.waypoints[0].z)
            self._publish_progress(
                "mission.progress",
                payload={
                    "waypoint_index": i,
                    "kind": wp.kind,
                    "state": self._fc.get_state().value,
                },
            )

        self._publish_progress("mission.finished", payload={"aborted": aborted})
        report = self._builder.finalize(finished_utc=self._clock())
        return MissionRunResult(
            report=report,
            aborted=aborted,
            abort_reason=abort_reason,
        )

    # -----------------------------------------------------------------

    def _execute(self, wp: Waypoint, *, takeoff_height_m: float) -> None:
        if wp.kind == "takeoff":
            self._fc.arm()
            self._fc.takeoff(takeoff_height_m)
            return
        if wp.kind == "landing":
            self._fc.land()
            return
        self._fc.goto(wp.x, wp.y, wp.z, wp.yaw_deg)
        if wp.capture:
            frame = self._cam.capture(self._fc.get_pose())
            self._builder.record(self._sink.consume(wp, frame))

    def _handle_abort(self) -> None:
        """Convince the drone to the ground: land if airborne or hovering,
        disarm if merely armed (ISC-27 LAND_NOW)."""
        state = self._fc.get_state()
        if state is ControllerState.AIRBORNE or state is ControllerState.SAFE_HOVER:
            self._fc.land()
        elif state is ControllerState.ARMED:
            self._fc.disarm()

    def _publish_progress(self, topic: str, *, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            topic,
            {
                "topic": topic,
                "timestamp_ns": int(self._clock().timestamp() * 1_000_000_000),
                "payload": payload,
            },
        )
