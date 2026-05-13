"""Tests for the `python -m closedSpace.run` CLI shim.

Covers ISC-26 (plan summary printed + explicit confirmation) plus the
exit-code contract used by CI / shell wrappers.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from closedSpace.run import (
    EXIT_MISSION_ABORTED,
    EXIT_OK,
    EXIT_OPERATOR_DECLINED,
    EXIT_PREFLIGHT_FAILED,
    main,
)

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--map",
        str(REFERENCE_MAP),
        "--output-root",
        str(tmp_path),
        "--allow-stale-map",  # reference fixture's surveyed_at may age out
        *extra,
    ]


# ---------------------------------------------------------------------------
# ISC-26 — plan summary printed; explicit "yes" required to proceed
# ---------------------------------------------------------------------------


def test_summary_is_printed_before_prompt(tmp_path: Path) -> None:
    out = io.StringIO()
    in_ = io.StringIO("no\n")  # operator declines
    main(_argv(tmp_path), stdin=in_, stdout=out)

    text = out.getvalue()
    assert "Mission plan" in text
    assert "Capture waypoints:" in text
    assert "Path length:" in text
    # Prompt MUST appear before the operator's input is required.
    assert "Proceed with mission?" in text


def test_decline_prevents_mission(tmp_path: Path) -> None:
    out = io.StringIO()
    in_ = io.StringIO("no\n")
    code = main(_argv(tmp_path), stdin=in_, stdout=out)
    assert code == EXIT_OPERATOR_DECLINED
    # No mission directories produced under output-root.
    assert list(tmp_path.glob("m-*")) == []


def test_yes_runs_mission_and_writes_report(tmp_path: Path) -> None:
    out = io.StringIO()
    in_ = io.StringIO("yes\n")
    # CLI defaults use spec gate thresholds (4 MP). Sim emits 16×16 frames,
    # so the mission completes but every capture is gated out → coverage 0%.
    # That's still a valid run; the CLI's job is to deliver a report.
    code = main(_argv(tmp_path), stdin=in_, stdout=out)
    assert code == EXIT_OK
    mission_dirs = list(tmp_path.glob("m-*"))
    assert len(mission_dirs) == 1
    report_path = mission_dirs[0] / "mission_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text())
    assert report["planned_waypoints"] == 64
    # All captures gated out under default thresholds — exact arithmetic
    # still puts coverage_pct at 0.
    assert report["coverage_pct"] == 0.0


# ---------------------------------------------------------------------------
# ISC-28 — preflight failure aborts before confirmation prompt
# ---------------------------------------------------------------------------


def test_preflight_failure_returns_failed_exit_code(tmp_path: Path) -> None:
    out = io.StringIO()
    in_ = io.StringIO("yes\n")  # would say yes if asked
    code = main(
        _argv(tmp_path),
        stdin=in_,
        stdout=out,
        battery_pct=lambda: 5.0,  # below the 30% floor
    )
    assert code == EXIT_PREFLIGHT_FAILED
    assert "Preflight FAILED" in out.getvalue()
    # CLI must not have advanced to the confirmation prompt.
    assert "Proceed with mission?" not in out.getvalue()


# ---------------------------------------------------------------------------
# Misc: bare invocation surface
# ---------------------------------------------------------------------------


def test_help_includes_required_flag() -> None:
    """argparse '--help' lists --map and --allow-stale-map."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "closedSpace.run", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--map" in result.stdout
    assert "--allow-stale-map" in result.stdout


def test_exit_codes_are_distinct() -> None:
    # Smoke: the four documented exit codes are all distinct integers.
    codes = {EXIT_OK, EXIT_PREFLIGHT_FAILED, EXIT_OPERATOR_DECLINED, EXIT_MISSION_ABORTED}
    assert len(codes) == 4
