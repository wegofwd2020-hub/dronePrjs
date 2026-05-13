"""Tests for :func:`closedSpace.mission.plan`.

These probes satisfy ISC-6 through ISC-10 plus the §10.4 determinism
requirement. The reference fixture is the spine of validation; one
synthetic blocked-transit case exercises the no-go-zone rejection path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from closedSpace.map import load
from closedSpace.mission import MissionConfig, TransitBlockedError, plan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE_MAP = FIXTURES / "maps" / "reference_warehouse.yaml"
REFERENCE_PLAN = FIXTURES / "missions" / "reference_plan.json"


@pytest.fixture(scope="module")
def reference_expected() -> dict[str, object]:
    with REFERENCE_PLAN.open() as f:
        return json.load(f)["expected"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# ISC-6: one capture waypoint per declared (aisle, rack, level) tuple
# ---------------------------------------------------------------------------


def test_capture_waypoint_count_matches_map(reference_expected: dict[str, object]) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m)

    declared = sum(
        len(rack.levels)
        for aisle in m.aisles
        for racks in aisle.racks.values()
        for rack in racks
    )
    assert p.capture_count == declared == reference_expected["capture_count"]


def test_capture_waypoints_cover_every_declared_tuple() -> None:
    """Every declared (aisle_id, rack_id, level_index) appears exactly once."""
    m = load(REFERENCE_MAP)
    p = plan(m)

    declared: set[tuple[str, str, int]] = {
        (aisle.id, rack.id, level.index)
        for aisle in m.aisles
        for racks in aisle.racks.values()
        for rack in racks
        for level in rack.levels
    }
    seen: set[tuple[str, str, int]] = {
        (
            str(w.metadata["aisle_id"]),
            str(w.metadata["rack_id"]),
            int(w.metadata["level_index"]),
        )
        for w in p.waypoints
        if w.capture
    }
    assert seen == declared


# ---------------------------------------------------------------------------
# ISC-7: total path length matches hand-computed reference within ±5%
# ---------------------------------------------------------------------------


def test_path_length_within_tolerance(reference_expected: dict[str, object]) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m)

    target = float(reference_expected["path_length_m"])  # type: ignore[arg-type]
    tol_pct = float(reference_expected["path_length_tolerance_pct"])  # type: ignore[arg-type]
    delta_pct = abs(p.path_length_m - target) / target * 100.0
    assert delta_pct <= tol_pct, (
        f"path length {p.path_length_m:.4f} deviates {delta_pct:.2f}% "
        f"from reference {target:.4f} (allowed ±{tol_pct}%)"
    )


# ---------------------------------------------------------------------------
# ISC-8: estimated duration is reported and stays under the cap
# ---------------------------------------------------------------------------


def test_est_duration_under_cap() -> None:
    m = load(REFERENCE_MAP)
    cfg = MissionConfig()
    p = plan(m, cfg)
    assert 0 < p.est_duration_s <= cfg.max_mission_duration_s


# ---------------------------------------------------------------------------
# ISC-9: boustrophedon — consecutive aisles enter from opposite ends
# ---------------------------------------------------------------------------


def test_boustrophedon_alternates_entry() -> None:
    """Aisle k=0 enters at start; k=1 enters at end (direction = any)."""
    m = load(REFERENCE_MAP)
    p = plan(m)

    # Pull the "enter" transit waypoints in declaration order.
    enters = [
        w
        for w in p.waypoints
        if w.kind == "transit" and w.metadata.get("phase") == "enter"
    ]
    assert len(enters) == len(m.aisles)

    # A1 (north-bound centerline 1.5→6.5): entry at start (y=1.5).
    # A2: alternated → entry at end (y=6.5).
    assert enters[0].y == pytest.approx(m.aisles[0].centerline.start.y)
    assert enters[1].y == pytest.approx(m.aisles[1].centerline.end.y)


# ---------------------------------------------------------------------------
# ISC-10: a no-go zone blocking a planned segment is rejected
# ---------------------------------------------------------------------------


def test_reference_plan_does_not_enter_no_go_zone() -> None:
    """Reference fixture's column zone sits between A1 and A2 but off the
    inter-aisle transit altitude path (y=6.5). plan() must succeed and
    no waypoint may sit inside the zone's XY polygon.
    """
    m = load(REFERENCE_MAP)
    p = plan(m)
    zone = m.no_go_zones[0]
    xs = [pt.x for pt in zone.polygon]
    ys = [pt.y for pt in zone.polygon]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    for w in p.waypoints:
        inside = x_lo <= w.x <= x_hi and y_lo <= w.y <= y_hi
        assert not inside, f"waypoint {w} sits inside no-go zone {zone.id!r}"


def test_blocking_no_go_zone_raises(tmp_path: Path) -> None:
    """A no-go zone straddling the inter-aisle transit aborts planning.

    Two aisles (A1 at x=3, A2 at x=13) with centerline ends at y=5.5
    plus a "wall" zone at x∈[5.5,10.5], y∈[5.0,6.0]: the natural
    straight-line transit from A1's exit (3, 5.5) to A2's entry (13, 5.5)
    crosses the zone's interior, so the planner must reject.
    """
    src = tmp_path / "blocked.yaml"
    src.write_text(
        "schema_version: '1.0'\n"
        "warehouse_id: 'block-1'\n"
        "units: meters\n"
        "coverage_polygon: [[0,0],[20,0],[20,10],[0,10]]\n"
        "takeoff_pad: {position: [1.0, 1.0, 0.0], yaw_deg: 0, radius_m: 0.5}\n"
        "no_go_zones:\n"
        "  - id: 'wall'\n"
        "    polygon: [[5.5, 5.0], [10.5, 5.0], [10.5, 6.0], [5.5, 6.0]]\n"
        "    z_min: 0.0\n"
        "    z_max: 5.0\n"
        "aisles:\n"
        "  - id: 'A1'\n"
        "    centerline: {start: [3.0, 1.5], end: [3.0, 5.5]}\n"
        "    width_m: 1.4\n"
        "    direction: any\n"
        "    racks: {}\n"
        "  - id: 'A2'\n"
        "    centerline: {start: [13.0, 1.5], end: [13.0, 5.5]}\n"
        "    width_m: 1.4\n"
        "    direction: any\n"
        "    racks: {}\n"
    )
    m = load(src)
    with pytest.raises(TransitBlockedError) as exc:
        plan(m)
    assert exc.value.zone_id == "wall"


# ---------------------------------------------------------------------------
# §10.4: determinism — same input → identical bytes
# ---------------------------------------------------------------------------


def test_plan_is_deterministic() -> None:
    m = load(REFERENCE_MAP)
    a = plan(m)
    b = plan(m)
    assert a == b
    # Belt-and-braces: serialize and compare bytes.
    def serialize(p_: object) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(p_), sort_keys=True, default=str)  # type: ignore[arg-type]

    assert serialize(a) == serialize(b)


# ---------------------------------------------------------------------------
# Bonus: structural shape (takeoff first, landing last, expected count)
# ---------------------------------------------------------------------------


def test_plan_shape(reference_expected: dict[str, object]) -> None:
    m = load(REFERENCE_MAP)
    p = plan(m)
    assert len(p.waypoints) == reference_expected["waypoint_count"]
    assert p.waypoints[0].kind == "takeoff"
    assert p.waypoints[-1].kind == "landing"
