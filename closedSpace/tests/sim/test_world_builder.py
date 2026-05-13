"""Tests for :mod:`closedSpace.sim.world_builder`.

The world builder is a pure function from :class:`Map` to SDF string;
tests pin both the structural shape of the output (correct counts,
parseable XML, named models) and the numeric geometry against
hand-computed expectations from the reference fixture.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from closedSpace.map import load
from closedSpace.map.types import (
    Aisle,
    Centerline,
    Level,
    Map,
    Point2D,
    Point3D,
    Rack,
    TakeoffPad,
)
from closedSpace.sim.world_builder import RACK_DEPTH_M, RACK_TOP_BUFFER_M, build_sdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE_MAP = FIXTURES / "maps" / "reference_warehouse.yaml"


@pytest.fixture(scope="module")
def reference_sdf() -> str:
    return build_sdf(load(REFERENCE_MAP))


# ---------------------------------------------------------------------------
# Structural shape
# ---------------------------------------------------------------------------


def test_sdf_is_valid_xml(reference_sdf: str) -> None:
    root = ET.fromstring(reference_sdf)
    assert root.tag == "sdf"
    assert root.attrib["version"] == "1.10"
    worlds = root.findall("world")
    assert len(worlds) == 1
    assert worlds[0].attrib["name"] == "ref-wh-01"


def test_one_rack_model_per_declared_rack(reference_sdf: str) -> None:
    """16 racks in the fixture → 16 ``rack_*`` models in the SDF."""
    root = ET.fromstring(reference_sdf)
    rack_names = [
        m.attrib["name"]
        for m in root.find("world").findall("model")  # type: ignore[union-attr]
        if m.attrib["name"].startswith("rack_")
    ]
    expected = {f"rack_{aisle}-{side}{idx}"
                for aisle in ("A1", "A2")
                for side in ("W", "E")
                for idx in (1, 2, 3, 4)}
    assert set(rack_names) == expected
    assert len(rack_names) == 16


def test_no_go_zone_present(reference_sdf: str) -> None:
    root = ET.fromstring(reference_sdf)
    names = {
        m.attrib["name"] for m in root.find("world").findall("model")  # type: ignore[union-attr]
    }
    assert "no_go_support_column_between_aisles" in names


def test_ground_plane_and_takeoff_marker_present(reference_sdf: str) -> None:
    root = ET.fromstring(reference_sdf)
    names = {
        m.attrib["name"] for m in root.find("world").findall("model")  # type: ignore[union-attr]
    }
    assert "ground_plane" in names
    assert "takeoff_pad_marker" in names


def test_includes_required_gazebo_plugins(reference_sdf: str) -> None:
    """Phase 3 needs physics + sensors + scene broadcaster wired in."""
    for plugin in (
        "gz-sim-physics-system",
        "gz-sim-user-commands-system",
        "gz-sim-scene-broadcaster-system",
        "gz-sim-sensors-system",
    ):
        assert plugin in reference_sdf


# ---------------------------------------------------------------------------
# Geometry — hand-checked against the reference fixture
# ---------------------------------------------------------------------------


def _rack_pose(sdf: str, rack_id: str) -> tuple[float, float, float, float]:
    """Extract ``(x, y, z, yaw)`` from the named rack model's pose."""
    root = ET.fromstring(sdf)
    for model in root.find("world").findall("model"):  # type: ignore[union-attr]
        if model.attrib["name"] == f"rack_{rack_id}":
            pose = model.find("pose").text.strip().split()  # type: ignore[union-attr]
            return float(pose[0]), float(pose[1]), float(pose[2]), float(pose[5])
    raise AssertionError(f"rack_{rack_id} not found in SDF")


def _rack_box_size(sdf: str, rack_id: str) -> tuple[float, float, float]:
    root = ET.fromstring(sdf)
    for model in root.find("world").findall("model"):  # type: ignore[union-attr]
        if model.attrib["name"] == f"rack_{rack_id}":
            size = (
                model.find("link/collision/geometry/box/size")  # type: ignore[union-attr]
                .text.strip()
                .split()
            )
            return float(size[0]), float(size[1]), float(size[2])
    raise AssertionError(f"rack_{rack_id} not found in SDF")


def test_a1_w1_geometry(reference_sdf: str) -> None:
    """A1-W1: centerline (3.0, 1.5)→(3.0, 6.5), position_along=0.7, west.

    Centerline direction = (0, 1). Perpendicular west = (-1, 0).
    Rack front face = (3.0, 2.2) + 1.2 * (-1, 0) = (1.8, 2.2).
    Box centroid = face + (RACK_DEPTH_M/2) * (-1, 0) = (1.8 - 0.2, 2.2) = (1.6, 2.2).
    Highest level is 3.5 m, so box height = 3.5 + 0.3 = 3.8 m, centroid z = 1.9.
    Yaw = atan2(1, 0) = pi/2.
    """
    x, y, z, yaw = _rack_pose(reference_sdf, "A1-W1")
    assert x == pytest.approx(1.6, abs=1e-6)
    assert y == pytest.approx(2.2, abs=1e-6)
    assert z == pytest.approx((3.5 + RACK_TOP_BUFFER_M) / 2.0, abs=1e-6)
    assert yaw == pytest.approx(math.pi / 2, abs=1e-6)

    sx, sy, sz = _rack_box_size(reference_sdf, "A1-W1")
    assert sx == pytest.approx(1.2, abs=1e-6)
    assert sy == pytest.approx(RACK_DEPTH_M, abs=1e-6)
    assert sz == pytest.approx(3.5 + RACK_TOP_BUFFER_M, abs=1e-6)


def test_a1_e1_mirrors_a1_w1_across_centerline(reference_sdf: str) -> None:
    """A1-E1 should be at x=4.4 (3.0 centerline + 1.2 half-width + 0.2 half-depth)."""
    x, y, _, yaw = _rack_pose(reference_sdf, "A1-E1")
    assert x == pytest.approx(4.4, abs=1e-6)
    assert y == pytest.approx(2.2, abs=1e-6)
    # Yaw is the centerline direction — same for both sides.
    assert yaw == pytest.approx(math.pi / 2, abs=1e-6)


def test_a2_w4_position_along(reference_sdf: str) -> None:
    """A2-W4: position_along=4.3 on aisle starting at y=1.5 → y=5.8."""
    x, y, _, _ = _rack_pose(reference_sdf, "A2-W4")
    assert x == pytest.approx(8.0 - 1.2 - RACK_DEPTH_M / 2.0, abs=1e-6)
    assert y == pytest.approx(1.5 + 4.3, abs=1e-6)


# ---------------------------------------------------------------------------
# Determinism + invariants
# ---------------------------------------------------------------------------


def test_build_sdf_is_deterministic() -> None:
    m = load(REFERENCE_MAP)
    a = build_sdf(m)
    b = build_sdf(m)
    assert a == b


def test_rejects_non_rectangular_coverage_polygon() -> None:
    """v1 only supports axis-aligned rectangles; reject anything else loudly."""
    triangular_map = Map(
        schema_version="1.0",
        warehouse_id="bad",
        units="meters",
        coverage_polygon=(Point2D(0.0, 0.0), Point2D(5.0, 0.0), Point2D(2.5, 5.0)),
        takeoff_pad=TakeoffPad(position=Point3D(1.0, 1.0, 0.0), yaw_deg=0, radius_m=0.5),
        no_go_zones=(),
        aisles=(),
    )
    with pytest.raises(ValueError, match="rectangular"):
        build_sdf(triangular_map)


def test_east_west_aisle_yaw_is_zero() -> None:
    """A horizontal aisle should rotate racks 0 rad (length along world x)."""
    horizontal_map = Map(
        schema_version="1.0",
        warehouse_id="ew",
        units="meters",
        coverage_polygon=(
            Point2D(0.0, 0.0),
            Point2D(10.0, 0.0),
            Point2D(10.0, 5.0),
            Point2D(0.0, 5.0),
        ),
        takeoff_pad=TakeoffPad(position=Point3D(0.5, 0.5, 0.0), yaw_deg=0, radius_m=0.3),
        no_go_zones=(),
        aisles=(
            Aisle(
                id="H1",
                centerline=Centerline(start=Point2D(1.0, 2.5), end=Point2D(9.0, 2.5)),
                width_m=2.4,
                direction="any",
                racks={
                    "south": (
                        Rack(
                            id="H1-S1",
                            position_along=1.0,
                            length_m=1.2,
                            face_offset_m=0.6,
                            yaw_deg=180,
                            levels=(Level(index=0, height_m=1.0),),
                        ),
                    ),
                },
            ),
        ),
    )
    sdf = build_sdf(horizontal_map)
    _, _, _, yaw = _rack_pose(sdf, "H1-S1")
    assert yaw == pytest.approx(0.0, abs=1e-6)
