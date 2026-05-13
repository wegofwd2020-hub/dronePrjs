"""Tests for :class:`closedSpace.capture.CaptureSink`.

Covers gate accept/reject paths and ISC-17/18 sidecar + filename shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from closedSpace.capture import (
    CaptureMissed,
    CaptureRecorded,
    CaptureSink,
    MissReason,
)
from closedSpace.mission import Waypoint
from closedSpace.storage import LocalSink
from engine.sensors import Frame
from engine.types import Pose


def _wp() -> Waypoint:
    return Waypoint(
        x=2.4,
        y=2.2,
        z=0.5,
        yaw_deg=270.0,
        kind="capture",
        metadata={"aisle_id": "A1", "rack_id": "A1-W1", "level_index": 0},
    )


def _frame(width: int = 2000, height: int = 2000, focus: float = 500.0) -> Frame:
    return Frame(
        pixels=b"\x80" * (width * height),
        width=width,
        height=height,
        pose=Pose(2.4, 2.2, 0.5, 270.0, timestamp_ns=42),
        focus_score=focus,
    )


def _sink(tmp_path: Path, **overrides: object) -> CaptureSink:
    defaults: dict[str, object] = dict(
        warehouse_id="ref-wh-01",
        mission_id="m-test",
        storage=LocalSink(tmp_path / "m"),
        min_capture_resolution_px=4_000_000,
        min_focus_score=100.0,
        clock=lambda: datetime(2026, 5, 13, 10, 0, 0, 123456, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return CaptureSink(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_recorded_outcome_persists_image_and_sidecar(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    outcome = sink.consume(_wp(), _frame())
    assert isinstance(outcome, CaptureRecorded)
    assert outcome.artifact.image_path.exists()
    assert outcome.artifact.sidecar_path.exists()


def test_sidecar_contains_isc17_fields(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    outcome = sink.consume(_wp(), _frame())
    assert isinstance(outcome, CaptureRecorded)
    side = json.loads(outcome.artifact.sidecar_path.read_text())
    # ISC-17 required keys
    expected = {
        "aisle_id",
        "rack_id",
        "level_index",
        "pose",
        "timestamp_utc",
        "mission_id",
        "image_uri",
    }
    assert expected.issubset(side.keys())
    # Pose substructure
    assert set(side["pose"].keys()) == {"x", "y", "z", "yaw_deg"}


def test_filename_matches_isc18_pattern(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    outcome = sink.consume(_wp(), _frame())
    assert isinstance(outcome, CaptureRecorded)
    # ISC-18: {warehouse_id}/{aisle_id}/{rack_id}/{level_index}/{timestamp}.{ext}
    parts = outcome.artifact.relative_path.split("/")
    assert parts[0] == "ref-wh-01"
    assert parts[1] == "A1"
    assert parts[2] == "A1-W1"
    assert parts[3] == "0"
    assert parts[4].endswith(".jpg")


# ---------------------------------------------------------------------------
# Gate rejection paths
# ---------------------------------------------------------------------------


def test_resolution_gate_rejects_undersized_frame(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    out = sink.consume(_wp(), _frame(width=16, height=16))
    assert isinstance(out, CaptureMissed)
    assert out.reason is MissReason.LOW_RESOLUTION


def test_focus_gate_rejects_blurry_frame(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    out = sink.consume(_wp(), _frame(focus=10.0))
    assert isinstance(out, CaptureMissed)
    assert out.reason is MissReason.LOW_FOCUS


def test_consume_rejects_non_capture_waypoint(tmp_path: Path) -> None:
    sink = _sink(tmp_path)
    transit = Waypoint(0, 0, 1, 0, kind="transit")
    with pytest.raises(ValueError, match="non-capture"):
        sink.consume(transit, _frame())


def test_loose_thresholds_let_sim_frames_through(tmp_path: Path) -> None:
    """The sim-sized override path the runner uses for in-process tests."""
    sink = _sink(
        tmp_path,
        min_capture_resolution_px=256,
        min_focus_score=10.0,
    )
    out = sink.consume(_wp(), _frame(width=16, height=16, focus=200.0))
    assert isinstance(out, CaptureRecorded)
