"""Tests for :class:`closedSpace.report.ReportBuilder`.

Covers ISC-23 (field set), ISC-24 (coverage_pct exact), ISC-25 (schema).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from closedSpace.capture import (
    CaptureMissed,
    CaptureRecorded,
    MissReason,
)
from closedSpace.mission import Waypoint
from closedSpace.report import ReportBuilder, ReportValidationError, validate_report
from closedSpace.storage import StoredArtifact


def _capture_wp(rack: str = "A1-W1", level: int = 0) -> Waypoint:
    return Waypoint(
        x=0,
        y=0,
        z=0.5,
        yaw_deg=0,
        kind="capture",
        metadata={"aisle_id": "A1", "rack_id": rack, "level_index": level},
    )


def _recorded(wp: Waypoint) -> CaptureRecorded:
    return CaptureRecorded(
        waypoint=wp,
        artifact=StoredArtifact(
            image_path=Path("/tmp/x.jpg"),
            sidecar_path=Path("/tmp/x.jpg.json"),
            relative_path="x.jpg",
        ),
        focus_score=500.0,
        width=2000,
        height=2000,
    )


def _missed(wp: Waypoint, reason: MissReason = MissReason.LOW_FOCUS) -> CaptureMissed:
    return CaptureMissed(waypoint=wp, reason=reason, detail="example")


def _builder(planned: int = 4) -> ReportBuilder:
    return ReportBuilder(
        mission_id="m-test",
        warehouse_id="ref-wh-01",
        map_id="ref-wh-01",
        started_utc=datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc),
        planned_capture_count=planned,
    )


def test_full_coverage_yields_100_pct() -> None:
    b = _builder(planned=4)
    for level in range(4):
        b.record(_recorded(_capture_wp(level=level)))
    report = b.finalize()
    assert report["captured_waypoints"] == 4
    assert report["coverage_pct"] == 100.0
    assert report["missed_waypoints"] == []


def test_partial_coverage_uses_exact_arithmetic() -> None:
    """ISC-24: coverage_pct == captured / planned * 100, no rounding."""
    b = _builder(planned=3)
    b.record(_recorded(_capture_wp(level=0)))
    b.record(_missed(_capture_wp(level=1), MissReason.LOW_RESOLUTION))
    b.record(_missed(_capture_wp(level=2), MissReason.STORAGE_ERROR))
    report = b.finalize()
    assert report["captured_waypoints"] == 1
    assert report["coverage_pct"] == 1 / 3 * 100.0  # 33.33333…
    reasons = [m["reason"] for m in report["missed_waypoints"]]
    assert reasons == ["low_resolution", "storage_error"]


def test_zero_planned_yields_zero_coverage_not_divide_by_zero() -> None:
    b = _builder(planned=0)
    report = b.finalize()
    assert report["coverage_pct"] == 0.0


def test_report_has_all_isc23_top_level_fields() -> None:
    """ISC-23: planned + captured + missed + coverage_pct + telemetry_summary."""
    b = _builder(planned=2)
    b.record(_recorded(_capture_wp(level=0)))
    b.record_state_transition()
    b.record_state_transition()
    report = b.finalize()
    expected = {
        "schema_version",
        "mission_id",
        "warehouse_id",
        "map_id",
        "started_utc",
        "finished_utc",
        "planned_waypoints",
        "captured_waypoints",
        "missed_waypoints",
        "coverage_pct",
        "telemetry_summary",
    }
    assert set(report.keys()) == expected
    assert report["telemetry_summary"]["state_transitions"] == 2


def test_finalize_validates_against_schema() -> None:
    """ISC-25: builder's own output passes schema validation."""
    b = _builder(planned=1)
    b.record(_recorded(_capture_wp(level=0)))
    # finalize() runs validate_report internally — would raise on mismatch.
    report = b.finalize()
    validate_report(report)  # idempotent re-check


def test_validate_rejects_bogus_report() -> None:
    """A malformed report raises ReportValidationError, not a raw jsonschema error."""
    with pytest.raises(ReportValidationError, match="schema validation"):
        validate_report({"schema_version": "1.0"})  # missing required fields
