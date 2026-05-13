"""Tests for the pre-arm checklist.

Each individual check has its own happy + sad path; the aggregate
:class:`PreflightResult.can_arm` covers the ISC-28 "blocks arm on
failure" contract.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from closedSpace.map import load
from closedSpace.operator import PreflightChecklist, PreflightOutcome

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def _checklist(
    *,
    battery: float = 95.0,
    calibration: bool = True,
    today: date = date(2026, 5, 1),
    allow_stale: bool = False,
) -> PreflightChecklist:
    return PreflightChecklist(
        battery_pct=lambda: battery,
        calibration_ok=lambda: calibration,
        today=lambda: today,
        allow_stale_map=allow_stale,
    )


# ---------------------------------------------------------------------------
# Happy path: clean map + fresh survey + healthy platform → can_arm
# ---------------------------------------------------------------------------


def test_reference_passes_under_healthy_conditions() -> None:
    m = load(REFERENCE_MAP)  # surveyed_at = 2026-04-15
    result = _checklist().run(m)
    assert result.can_arm
    assert all(c.outcome is PreflightOutcome.PASS for c in result.checks)


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------


def test_low_battery_fails_preflight() -> None:
    m = load(REFERENCE_MAP)
    result = _checklist(battery=15.0).run(m)
    assert not result.can_arm
    failed = {c.name for c in result.failures}
    assert "battery" in failed


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_failed_calibration_fails_preflight() -> None:
    m = load(REFERENCE_MAP)
    result = _checklist(calibration=False).run(m)
    assert not result.can_arm
    assert "calibration" in {c.name for c in result.failures}


# ---------------------------------------------------------------------------
# ISC-34 — takeoff in coverage
# ---------------------------------------------------------------------------


def test_takeoff_outside_coverage_fails(tmp_path: Path) -> None:
    """A map with takeoff outside the polygon must fail preflight.

    We can't load such a map via the normal loader (semantic validation
    rejects it during load). We bypass by constructing the Map directly
    with field overrides — checklist takes a Map, not a YAML path.
    """
    from dataclasses import replace
    from closedSpace.map.types import Point3D, TakeoffPad

    m = load(REFERENCE_MAP)
    bad = replace(
        m,
        takeoff_pad=TakeoffPad(
            position=Point3D(99.0, 99.0, 0.0),
            yaw_deg=0.0,
            radius_m=0.5,
        ),
    )
    result = _checklist().run(bad)
    assert not result.can_arm
    failures = {c.name: c for c in result.failures}
    assert "takeoff_in_coverage" in failures
    assert "OUTSIDE coverage polygon" in failures["takeoff_in_coverage"].detail


# ---------------------------------------------------------------------------
# ISC-44 — map staleness
# ---------------------------------------------------------------------------


def test_fresh_map_passes_staleness_check() -> None:
    m = load(REFERENCE_MAP)  # surveyed 2026-04-15
    # 14 days later: under 30-day threshold.
    result = _checklist(today=date(2026, 4, 29)).run(m)
    assert result.can_arm


def test_stale_map_fails_by_default() -> None:
    m = load(REFERENCE_MAP)  # surveyed 2026-04-15
    # 90 days later: well over 30-day threshold.
    result = _checklist(today=date(2026, 7, 15)).run(m)
    assert not result.can_arm
    assert "map_staleness" in {c.name for c in result.failures}


def test_allow_stale_map_demotes_to_warn() -> None:
    m = load(REFERENCE_MAP)
    result = _checklist(today=date(2026, 7, 15), allow_stale=True).run(m)
    # Other checks still pass; staleness demoted to warn, not fail.
    assert result.can_arm
    stale = next(c for c in result.checks if c.name == "map_staleness")
    assert stale.outcome is PreflightOutcome.WARN


def test_null_surveyed_at_is_warn_not_fail(tmp_path: Path) -> None:
    """ISC-44: null surveyed_at → non-blocking warning, not failure."""
    from dataclasses import replace

    m = load(REFERENCE_MAP)
    no_provenance = replace(m, surveyed_at=None, surveyed_by=None)
    result = _checklist().run(no_provenance)
    assert result.can_arm  # non-blocking
    stale = next(c for c in result.checks if c.name == "map_staleness")
    assert stale.outcome is PreflightOutcome.WARN
    assert "null" in stale.detail
