"""Map → MissionPlan derivation.

Implements the path-derivation contract in ``docs/map-schema.md`` §10.
The function :func:`plan` is **pure**: same map + same config → identical
output, byte-for-byte. No IO, no randomness, no time-of-day inputs.

§10.2 vs §10.2.3.2 resolution
-----------------------------
The spec says boustrophedon alternates entry ends "so total transit is
minimized" (§10.2.2), AND that racks are visited "in declared
position_along order" (§10.2.3.2). On an aisle entered at its END, those
two rules conflict — literal pos_along ordering would force the drone
to fly past every rack to the lowest pos_along before sweeping back.
This planner honors the *intent* (§10.2.2 + ISC-9) and visits racks in
**entry-direction physical order**: forward when entering at start,
reversed when entering at end. The waypoint metadata still reports the
declared rack/level ids; only the visit order changes.
"""
from __future__ import annotations

import math
from typing import Iterable

from closedSpace.map.types import Aisle, Direction, Map, Point2D, Rack, SideName
from closedSpace.mission.transit import verify_segments
from closedSpace.mission.types import MissionConfig, MissionPlan, Waypoint

#: Per §10.2.3.2, sides are emitted in this canonical order. For a
#: north-south aisle only "west"/"east" are present; for an east-west
#: aisle only "north"/"south". Missing keys are skipped silently.
_SIDE_ORDER: tuple[SideName, ...] = ("west", "east", "south", "north")


def plan(m: Map, config: MissionConfig | None = None) -> MissionPlan:
    """Derive a :class:`MissionPlan` from a validated :class:`Map`.

    Args:
        m: A loaded map.
        config: Per-mission tunables. ``None`` uses the §10.3 defaults.

    Returns:
        An immutable :class:`MissionPlan` containing the full ordered
        waypoint sequence plus aggregate metrics.

    Raises:
        TransitBlockedError: A segment in the resulting polyline crosses
            a no-go zone. v1 has no rerouter; the plan is rejected.
    """
    cfg = config or MissionConfig()

    waypoints: list[Waypoint] = [_takeoff(m, cfg)]

    for k, aisle in enumerate(m.aisles):
        enter_at_end = _enter_at_end(k, aisle)
        waypoints.extend(_aisle_waypoints(aisle, enter_at_end, cfg))

    waypoints.append(_landing(m, cfg))

    # ISC-10: every straight-line segment must clear all no-go zones.
    xy = [(w.x, w.y) for w in waypoints]
    verify_segments(xy, m.no_go_zones)

    path_length = _polyline_length_3d(waypoints)
    capture_count = sum(1 for w in waypoints if w.capture)
    est_duration = (
        path_length / cfg.nominal_speed_mps + capture_count * cfg.capture_dwell_s
    )

    return MissionPlan(
        waypoints=tuple(waypoints),
        path_length_m=path_length,
        est_duration_s=est_duration,
        capture_count=capture_count,
    )


# ---------------------------------------------------------------------------
# Per-section emitters
# ---------------------------------------------------------------------------


def _takeoff(m: Map, cfg: MissionConfig) -> Waypoint:
    pad = m.takeoff_pad
    return Waypoint(
        x=pad.position.x,
        y=pad.position.y,
        z=cfg.takeoff_height_m,
        yaw_deg=pad.yaw_deg,
        kind="takeoff",
    )


def _landing(m: Map, cfg: MissionConfig) -> Waypoint:
    pad = m.takeoff_pad
    return Waypoint(
        x=pad.position.x,
        y=pad.position.y,
        z=cfg.takeoff_height_m,
        yaw_deg=pad.yaw_deg,
        kind="landing",
    )


def _aisle_waypoints(
    aisle: Aisle, enter_at_end: bool, cfg: MissionConfig
) -> list[Waypoint]:
    """Emit transit-in, all captures, transit-out for one aisle."""
    start = aisle.centerline.start
    end = aisle.centerline.end
    entry, exit_ = (end, start) if enter_at_end else (start, end)

    out: list[Waypoint] = [
        Waypoint(
            x=entry.x,
            y=entry.y,
            z=cfg.aisle_traversal_height_m,
            yaw_deg=0.0,
            kind="transit",
            metadata={"aisle_id": aisle.id, "phase": "enter"},
        )
    ]

    for side in _SIDE_ORDER:
        racks = aisle.racks.get(side)
        if not racks:
            continue
        rack_iter = reversed(racks) if enter_at_end else iter(racks)
        for rack in rack_iter:
            out.extend(_rack_captures(aisle, rack, side))

    out.append(
        Waypoint(
            x=exit_.x,
            y=exit_.y,
            z=cfg.aisle_traversal_height_m,
            yaw_deg=0.0,
            kind="transit",
            metadata={"aisle_id": aisle.id, "phase": "exit"},
        )
    )
    return out


def _rack_captures(aisle: Aisle, rack: Rack, side: SideName) -> Iterable[Waypoint]:
    """Per §10.2.3.2.iii: one capture per level in index order."""
    cap_x, cap_y = _capture_xy(aisle, rack, side)
    for level in rack.levels:
        yield Waypoint(
            x=cap_x,
            y=cap_y,
            z=level.height_m,
            yaw_deg=rack.yaw_deg,
            kind="capture",
            metadata={
                "aisle_id": aisle.id,
                "rack_id": rack.id,
                "level_index": level.index,
            },
        )


def _capture_xy(aisle: Aisle, rack: Rack, side: SideName) -> tuple[float, float]:
    """Compute the (x, y) capture stand-off per §10.2.3.2.ii.

    The capture point sits ``width_m/2 - face_offset_m`` perpendicular
    to the centerline toward the requested side, at ``position_along``
    distance from the centerline start.
    """
    s = aisle.centerline.start
    e = aisle.centerline.end
    dx = e.x - s.x
    dy = e.y - s.y
    seg_len = math.hypot(dx, dy)
    # Unit vector along the centerline (start → end).
    ux, uy = dx / seg_len, dy / seg_len
    # Point along the centerline at the rack's position_along.
    px = s.x + ux * rack.position_along
    py = s.y + uy * rack.position_along
    # Perpendicular unit vectors. Right-hand normal of (ux, uy) is
    # (uy, -ux); left-hand is (-uy, ux). We map sides to these by the
    # aisle's centerline direction:
    #   north-bound aisle (uy > 0): right = east, left = west
    #   south-bound aisle (uy < 0): right = west, left = east
    #   east-bound  aisle (ux > 0): right = south, left = north
    #   west-bound  aisle (ux < 0): right = north, left = south
    right_side = _right_side_for(ux, uy)
    sign = 1.0 if side == right_side else -1.0
    nx, ny = uy * sign, -ux * sign
    offset = aisle.width_m / 2.0 - rack.face_offset_m
    return (px + nx * offset, py + ny * offset)


def _right_side_for(ux: float, uy: float) -> SideName:
    """Which compass side is on the right of a (ux, uy)-oriented centerline."""
    if abs(uy) >= abs(ux):
        return "east" if uy > 0 else "west"
    return "south" if ux > 0 else "north"


# ---------------------------------------------------------------------------
# Boustrophedon entry selection
# ---------------------------------------------------------------------------


def _enter_at_end(k: int, aisle: Aisle) -> bool:
    """Decide which centerline end this aisle is entered at.

    * If ``direction`` is "any", alternate by aisle index: even aisles
      enter at start, odd aisles at end. This is the boustrophedon
      pattern from §10.2.2.
    * Otherwise, the aisle declares a fixed direction; pick the entry
      that matches.
    """
    if aisle.direction == "any":
        return k % 2 == 1
    return _entry_from_direction(aisle.direction, aisle.centerline.start, aisle.centerline.end)


def _entry_from_direction(
    direction: Direction, start: Point2D, end: Point2D
) -> bool:
    """Map a declared compass direction to enter-at-end (True/False).

    e.g. ``north_to_south`` means the drone moves from high y to low y,
    so it enters the centerline at whichever endpoint has the larger y.
    """
    if direction == "north_to_south":
        return end.y < start.y  # enter at the northern (larger-y) endpoint
    if direction == "south_to_north":
        return end.y > start.y
    if direction == "east_to_west":
        return end.x < start.x
    if direction == "west_to_east":
        return end.x > start.x
    # "any" is handled in _enter_at_end; this branch shouldn't be hit.
    return False


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


def _polyline_length_3d(waypoints: list[Waypoint]) -> float:
    """Total Euclidean length of the waypoint polyline in 3D."""
    total = 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        total += math.sqrt(
            (b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2
        )
    return total
