"""Mission-report accumulator and validator."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema

from closedSpace.capture import CaptureMissed, CaptureOutcome, CaptureRecorded

#: Path to the JSON Schema bundled with the package.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "mission_report.schema.json"

#: Schema version this builder emits. Bumped only when fields move.
_REPORT_SCHEMA_VERSION = "1.0"


class ReportValidationError(Exception):
    """The composed report did not match its JSON Schema. A bug, not user input."""


class ReportBuilder:
    """Accumulates capture outcomes; produces and validates the report.

    The builder is stateful: call :meth:`record` once per
    :class:`~closedSpace.capture.CaptureOutcome` the mission runner
    receives, then :meth:`finalize` once with the wall-clock end time.
    """

    def __init__(
        self,
        *,
        mission_id: str,
        warehouse_id: str,
        map_id: str,
        started_utc: datetime,
        planned_capture_count: int,
    ) -> None:
        self._mission_id = mission_id
        self._warehouse_id = warehouse_id
        self._map_id = map_id
        self._started = started_utc
        self._planned = planned_capture_count
        self._captured = 0
        self._missed: list[dict[str, Any]] = []
        self._state_transitions = 0

    def record(self, outcome: CaptureOutcome) -> None:
        if isinstance(outcome, CaptureRecorded):
            self._captured += 1
            return
        if isinstance(outcome, CaptureMissed):
            wp = outcome.waypoint
            self._missed.append(
                {
                    "aisle_id": str(wp.metadata["aisle_id"]),
                    "rack_id": str(wp.metadata["rack_id"]),
                    "level_index": int(wp.metadata["level_index"]),
                    "reason": outcome.reason.value,
                    "detail": outcome.detail,
                }
            )
            return
        raise TypeError(f"unexpected outcome type: {type(outcome).__name__}")

    def record_state_transition(self) -> None:
        """Increment the telemetry summary's state-transition counter."""
        self._state_transitions += 1

    def finalize(self, finished_utc: datetime | None = None) -> dict[str, Any]:
        """Build, validate, and return the report dict."""
        finished = finished_utc or datetime.now(timezone.utc)
        coverage = (
            (self._captured / self._planned * 100.0) if self._planned else 0.0
        )
        report: dict[str, Any] = {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "mission_id": self._mission_id,
            "warehouse_id": self._warehouse_id,
            "map_id": self._map_id,
            "started_utc": self._started.isoformat(),
            "finished_utc": finished.isoformat(),
            "planned_waypoints": self._planned,
            "captured_waypoints": self._captured,
            "missed_waypoints": self._missed,
            "coverage_pct": coverage,
            "telemetry_summary": {"state_transitions": self._state_transitions},
        }
        validate_report(report)
        return report


def validate_report(report: dict[str, Any]) -> None:
    """Validate a report dict against the bundled JSON Schema."""
    schema = _load_schema()
    try:
        jsonschema.validate(instance=report, schema=schema)
    except jsonschema.ValidationError as e:
        field = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ReportValidationError(
            f"mission report failed schema validation at {field!r}: {e.message}"
        ) from e


def _load_schema() -> dict[str, Any]:
    try:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except FileNotFoundError as e:  # packaging error, not user input
        raise ReportValidationError(
            f"mission_report.schema.json not found at {_SCHEMA_PATH}"
        ) from e
