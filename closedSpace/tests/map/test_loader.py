"""Tests for :mod:`closedSpace.map.loader`.

These exercise :func:`load` end-to-end against the reference fixture and
against synthesized bad inputs. They satisfy the loader-side probes for
ISC-1, ISC-2, ISC-3, ISC-4, and ISC-5.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from closedSpace.map import (
    Map,
    MapError,
    MapValidationError,
    UnsupportedMapVersionError,
    load,
)

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def test_reference_loads() -> None:
    """ISC-1: reference fixture parses without exception."""
    m = load(REFERENCE_MAP)
    assert isinstance(m, Map)
    assert m.schema_version == "1.0"
    assert m.warehouse_id == "ref-wh-01"
    assert m.units == "meters"


def test_reference_has_two_aisles() -> None:
    """Reference fixture exposes the declared 2 aisles."""
    m = load(REFERENCE_MAP)
    assert len(m.aisles) == 2
    assert {a.id for a in m.aisles} == {"A1", "A2"}


def test_reference_total_capture_positions() -> None:
    """2 aisles × 2 sides × 4 racks × 4 levels = 64 capture positions."""
    m = load(REFERENCE_MAP)
    total = sum(
        len(rack.levels)
        for aisle in m.aisles
        for racks in aisle.racks.values()
        for rack in racks
    )
    assert total == 64


def test_reference_typed_attribute_access() -> None:
    """ISC-4: typed attribute access works for nested fields."""
    m = load(REFERENCE_MAP)
    a1 = next(a for a in m.aisles if a.id == "A1")
    rack = a1.racks["west"][0]
    level = rack.levels[2]
    assert level.index == 2
    assert level.height_m == 2.5
    assert rack.face_offset_m == 0.6


def test_load_missing_file_raises_map_error(tmp_path: Path) -> None:
    """File-not-found path raises :class:`MapError`, not bare FileNotFoundError."""
    with pytest.raises(MapError, match="not found"):
        load(tmp_path / "nope.yaml")


def test_load_invalid_yaml_raises_map_error(tmp_path: Path) -> None:
    """Malformed YAML raises :class:`MapError`."""
    p = tmp_path / "bad.yaml"
    p.write_text("aisles: [unterminated\n")
    with pytest.raises(MapError, match="not valid YAML"):
        load(p)


def test_load_non_mapping_root_raises_validation(tmp_path: Path) -> None:
    """Root that parses to a list (not a mapping) is rejected."""
    p = tmp_path / "list.yaml"
    p.write_text("- foo\n- bar\n")
    with pytest.raises(MapValidationError, match="root must be a mapping"):
        load(p)


def test_load_unsupported_version_raises(tmp_path: Path) -> None:
    """ISC-3: unsupported ``schema_version`` raises :class:`UnsupportedMapVersionError`."""
    p = tmp_path / "old.yaml"
    p.write_text(
        "schema_version: '0.9'\n"
        "warehouse_id: x\n"
        "units: meters\n"
        "coverage_polygon: [[0,0],[1,0],[1,1]]\n"
        "takeoff_pad:\n"
        "  position: [0.5, 0.5, 0.0]\n"
        "  yaw_deg: 0\n"
        "  radius_m: 0.1\n"
        "aisles: []\n"
    )
    with pytest.raises(UnsupportedMapVersionError) as exc:
        load(p)
    assert exc.value.version == "0.9"


def test_load_missing_required_field_raises(tmp_path: Path) -> None:
    """ISC-2: missing required field raises :class:`MapValidationError`."""
    p = tmp_path / "missing.yaml"
    p.write_text(
        "schema_version: '1.0'\n"
        "warehouse_id: x\n"
        "units: meters\n"
        # coverage_polygon intentionally omitted
        "takeoff_pad:\n"
        "  position: [1.0, 1.0, 0.0]\n"
        "  yaw_deg: 0\n"
        "  radius_m: 0.5\n"
        "aisles: []\n"
    )
    with pytest.raises(MapValidationError):
        load(p)
