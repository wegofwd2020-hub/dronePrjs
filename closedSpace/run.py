"""``python -m closedSpace.run`` — operator-facing mission entry point.

Loads a YAML map, plans the mission, prints a human-readable plan
summary, runs the pre-arm checklist, prompts for explicit confirmation,
then drives the mission against the in-process sim and writes the
final report. ISC-26 (summary + confirm) is the front-door criterion
this module owns.

Real-hardware bring-up (Phase 3 / D1 decision) replaces the sim wiring
with a platform adapter behind the same Protocols; the CLI stays the
same.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from closedSpace.capture import CaptureSink
from closedSpace.control import LinkLossWatchdog, SlamWatchdog
from closedSpace.map import Map, load
from closedSpace.mission import MissionConfig, MissionPlan, plan
from closedSpace.operator import (
    AbortSignal,
    MissionRunner,
    MissionRunResult,
    PreflightChecklist,
    PreflightOutcome,
    PreflightResult,
)
from closedSpace.report import ReportBuilder
from closedSpace.storage import LocalSink
from engine.sim import SimCamera, SimFlightController, SimLinkMonitor, SimSLAM, SimWorld
from engine.telemetry import InMemoryTelemetryBus, JSONLTelemetryLogger
from engine.types import Pose

#: Exit codes used by main() — kept stable so operators / CI can switch on them.
EXIT_OK = 0
EXIT_PREFLIGHT_FAILED = 2
EXIT_OPERATOR_DECLINED = 3
EXIT_MISSION_ABORTED = 4


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    battery_pct: Callable[[], float] | None = None,
    calibration_ok: Callable[[], bool] | None = None,
) -> int:
    """Entry point. Returns the shell exit code.

    Args:
        argv: argv slice (excluding program name). Defaults to ``sys.argv[1:]``.
        stdin / stdout: I/O streams. Injected so tests can drive the
            confirmation prompt without touching the real terminal.
        battery_pct / calibration_ok: platform callables. Defaults
            stub them to "100 %" / "OK" so the in-process sim path is
            runnable from a fresh checkout.
    """
    args = _parse_args(argv)
    out = stdout or sys.stdout
    in_ = stdin or sys.stdin

    m = load(args.map)
    p = plan(m, MissionConfig())
    _print_plan_summary(m, p, out)

    checklist = PreflightChecklist(
        battery_pct=battery_pct or (lambda: 100.0),
        calibration_ok=calibration_ok or (lambda: True),
        allow_stale_map=args.allow_stale_map,
    )
    preflight = checklist.run(m)
    _print_preflight(preflight, out)
    if not preflight.can_arm:
        out.write("\nPreflight FAILED — refusing to arm.\n")
        return EXIT_PREFLIGHT_FAILED

    if not _confirm(in_, out, prompt="Proceed with mission? [yes/no] "):
        out.write("Operator declined. No flight initiated.\n")
        return EXIT_OPERATOR_DECLINED

    result = _run_mission(m, p, args, out)
    if result.aborted:
        return EXIT_MISSION_ABORTED
    return EXIT_OK


# ---------------------------------------------------------------------------
# Argument parsing & I/O helpers
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="closedSpace.run",
        description="Run a closedSpace warehouse-inventory mission against the in-process sim.",
    )
    parser.add_argument(
        "--map",
        required=True,
        type=Path,
        help="Path to the YAML warehouse map (see closedSpace/docs/map-schema.md).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("./missions"),
        help="Directory under which per-mission folders are created.",
    )
    parser.add_argument(
        "--allow-stale-map",
        action="store_true",
        help=(
            "Permit arming against a map older than the staleness threshold. "
            "Has no effect on maps with null surveyed_at — those are always a warn."
        ),
    )
    return parser.parse_args(argv)


def _print_plan_summary(m: Map, p: MissionPlan, out: TextIO) -> None:
    out.write("=" * 60 + "\n")
    out.write(f"  Mission plan — warehouse: {m.warehouse_id}\n")
    out.write(f"  Map surveyed_at: {m.surveyed_at or '(unknown)'}\n")
    out.write("-" * 60 + "\n")
    out.write(f"  Aisles:                {len(m.aisles)}\n")
    out.write(f"  Capture waypoints:     {p.capture_count}\n")
    out.write(f"  Total waypoints:       {len(p.waypoints)}\n")
    out.write(f"  Path length:           {p.path_length_m:.2f} m\n")
    out.write(f"  Est. duration:         {p.est_duration_s:.0f} s "
              f"({p.est_duration_s / 60:.1f} min)\n")
    out.write("=" * 60 + "\n")


def _print_preflight(result: PreflightResult, out: TextIO) -> None:
    out.write("\nPreflight:\n")
    for c in result.checks:
        marker = {
            PreflightOutcome.PASS: "[OK]",
            PreflightOutcome.FAIL: "[FAIL]",
            PreflightOutcome.WARN: "[WARN]",
        }[c.outcome]
        out.write(f"  {marker:<8}{c.name:<24}{c.detail}\n")


def _confirm(in_: TextIO, out: TextIO, *, prompt: str) -> bool:
    """ISC-26: arming requires an explicit affirmative line from the operator."""
    out.write(prompt)
    out.flush()
    line = in_.readline().strip().lower()
    return line in {"yes", "y"}


def _run_mission(
    m: Map, p: MissionPlan, args: argparse.Namespace, out: TextIO
) -> MissionRunResult:
    mission_id = f"m-{uuid.uuid4().hex[:8]}"
    started = datetime.now(timezone.utc)
    mission_root = args.output_root / mission_id

    world = SimWorld()
    bus = InMemoryTelemetryBus()
    fc = SimFlightController(world, bus=bus)
    slam = SimSLAM(world)
    cam = SimCamera(world)
    slam.start()
    cam.start()

    storage = LocalSink(mission_root)
    # CLI default uses spec gate values. Real captures from real cameras
    # are expected to satisfy them; sim runs should override via a
    # programmatic entry point (used by tests) or be tolerated as
    # all-low-resolution missions reported as 0% coverage.
    cfg = MissionConfig()
    sink = CaptureSink(
        warehouse_id=m.warehouse_id,
        mission_id=mission_id,
        storage=storage,
        min_capture_resolution_px=cfg.min_capture_resolution_px,
        min_focus_score=cfg.min_focus_score,
    )
    builder = ReportBuilder(
        mission_id=mission_id,
        warehouse_id=m.warehouse_id,
        map_id=m.warehouse_id,
        started_utc=started,
        planned_capture_count=p.capture_count,
    )

    abort = AbortSignal()
    # ISC-15 home: the first waypoint is always "takeoff"; its (x,y)
    # is the pad center the drone returns to on link loss.
    takeoff_wp = p.waypoints[0]
    home_pose = Pose(
        x=takeoff_wp.x,
        y=takeoff_wp.y,
        z=takeoff_wp.z,  # hover height — descend via land()
        yaw_deg=0.0,
        timestamp_ns=world.now_ns(),
    )
    link_monitor = SimLinkMonitor(clock=world.now_ns)
    with JSONLTelemetryLogger(mission_root / "telemetry.jsonl") as logger:
        logger.attach(
            bus,
            "flight_control.state",
            "mission.started",
            "mission.progress",
            "mission.finished",
        )
        runner = MissionRunner(
            plan=p, fc=fc, cam=cam, sink=sink, builder=builder,
            bus=bus, abort_signal=abort,
            # ISC-12: SLAM loss → SAFE_HOVER watchdog, on the sim's clock
            # so StateChange timestamps and loss detection stay coherent.
            watchdog=SlamWatchdog(slam=slam, fc=fc, clock=world.now_ns),
            # ISC-15: ground-station link loss → RTH + land, same clock.
            link_watchdog=LinkLossWatchdog(
                link=link_monitor, fc=fc, home=home_pose, clock=world.now_ns
            ),
        )
        result = runner.run()

    report_path = mission_root / "mission_report.json"
    report_path.write_text(json.dumps(result.report, indent=2, sort_keys=True))
    out.write(f"\nMission complete. Report: {report_path}\n")
    out.write(f"  captured: {result.report['captured_waypoints']} / "
              f"{result.report['planned_waypoints']}\n")
    out.write(f"  coverage: {result.report['coverage_pct']:.2f}%\n")
    if result.aborted:
        out.write(f"  ABORTED: {result.abort_reason}\n")
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
