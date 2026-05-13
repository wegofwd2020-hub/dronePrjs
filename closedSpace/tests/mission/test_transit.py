"""Tests for :mod:`closedSpace.mission.transit`.

The planner exercises :func:`verify_segments` transitively, but a
direct test surface keeps the no-go-zone-rejection invariant visible
in coverage and pins the public API.
"""
from __future__ import annotations

import pytest

from closedSpace.map.types import NoGoZone, Point2D
from closedSpace.mission.transit import TransitBlockedError, verify_segments


def _zone(id_: str, xs: tuple[float, float], ys: tuple[float, float]) -> NoGoZone:
    """Build a rectangular no-go zone for the given x and y spans."""
    x_lo, x_hi = xs
    y_lo, y_hi = ys
    return NoGoZone(
        id=id_,
        polygon=(
            Point2D(x_lo, y_lo),
            Point2D(x_hi, y_lo),
            Point2D(x_hi, y_hi),
            Point2D(x_lo, y_hi),
        ),
        z_min=0.0,
        z_max=5.0,
    )


def test_verify_passes_for_clear_path() -> None:
    """A polyline that misses every zone returns without raising."""
    points = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]
    zones = [_zone("z1", (2.0, 3.0), (2.0, 3.0))]
    verify_segments(points, zones)  # no exception expected


def test_verify_raises_when_segment_crosses_zone() -> None:
    points = [(0.0, 1.0), (4.0, 1.0)]
    zones = [_zone("wall", (1.0, 3.0), (0.5, 1.5))]
    with pytest.raises(TransitBlockedError) as exc:
        verify_segments(points, zones)
    assert exc.value.zone_id == "wall"
    assert exc.value.segment_index == 0


def test_verify_no_zones_is_noop() -> None:
    """An empty zone list short-circuits without scanning segments."""
    verify_segments([(0.0, 0.0), (100.0, 100.0)], [])


def test_verify_under_two_points_is_noop() -> None:
    """A single point has no segment to verify."""
    verify_segments([(0.0, 0.0)], [_zone("z", (0, 1), (0, 1))])
