"""Inter-segment transit verification for v1 mission plans.

v1 routing is **naive**: every segment between consecutive waypoints is a
straight Euclidean line. This module's job is to *verify* that no such
segment passes through a no-go zone. If one does, the planner fails
loudly (:class:`TransitBlockedError`) — there's no fallback rerouter
yet. Smarter free-space routing is explicitly out of scope for v1 per
``docs/next-steps.md`` §1.3.

This satisfies the ISC-10 probe: "spatial intersection check on the
emitted waypoint list rejects any plan that would enter a no-go zone."
"""
from __future__ import annotations

from typing import Sequence

# Re-use the geometry helper already exercised by the map validator —
# duplicating a 30-line algorithm would invite drift. Underscore prefix
# acknowledges it's not currently part of the public surface; if a
# third caller appears, lift it into a shared closedSpace.geometry.
from closedSpace.map.types import NoGoZone
from closedSpace.map.validate import MapError, _segment_crosses_polygon


class TransitBlockedError(MapError):
    """A planned straight-line segment intersects a no-go zone.

    The planner has no rerouter in v1, so this aborts plan generation.
    """

    def __init__(self, segment_index: int, zone_id: str) -> None:
        super().__init__(
            f"transit segment {segment_index} is blocked by no_go_zone {zone_id!r}"
        )
        self.segment_index = segment_index
        self.zone_id = zone_id


def verify_segments(
    points_xy: Sequence[tuple[float, float]],
    no_go_zones: Sequence[NoGoZone],
) -> None:
    """Verify every consecutive segment is clear of every no-go zone.

    Args:
        points_xy: 2D projection of the waypoint polyline, in order. We
            only check XY because no-go zones in schema v1 are columnar
            (z_min/z_max define vertical extent, polygon defines XY) and
            v1's traversal height is fixed — a horizontal-only check is
            sufficient. Per-zone z-extent could be honored in a future
            pass when transit altitudes become variable.
        no_go_zones: Zones declared by the map.

    Raises:
        TransitBlockedError: A segment crosses a zone's polygon (XY).
    """
    if len(points_xy) < 2 or not no_go_zones:
        return
    for i in range(len(points_xy) - 1):
        p1 = points_xy[i]
        p2 = points_xy[i + 1]
        for zone in no_go_zones:
            polygon_lists = [[p.x, p.y] for p in zone.polygon]
            if _segment_crosses_polygon(p1, p2, polygon_lists):
                raise TransitBlockedError(segment_index=i, zone_id=zone.id)
