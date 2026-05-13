"""closedSpace.report — mission_report.json builder + validator.

One :class:`ReportBuilder` accumulates per-waypoint outcomes during a
mission and emits a single ``mission_report.json`` matching
``closedSpace/schemas/mission_report.schema.json``.

The builder also runs the schema validator on its own output before
returning — that's how ISC-25 (report validates) and ISC-24
(coverage_pct exact) are enforced in-process rather than as a
separate post-hoc CI step.
"""
from __future__ import annotations

from closedSpace.report.builder import (
    ReportBuilder,
    ReportValidationError,
    validate_report,
)

__all__ = ["ReportBuilder", "ReportValidationError", "validate_report"]
