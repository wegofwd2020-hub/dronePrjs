"""Tests for :func:`closedSpace.map.dump`.

The defining contract (ISC-5) is round-trip equality: ``load(dump(m)) == m``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from closedSpace.map import Map, MapError, dump, load

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


def test_round_trip_equality(tmp_path: Path) -> None:
    """ISC-5: dump → load yields a Map equal to the original."""
    original = load(REFERENCE_MAP)
    out = tmp_path / "round_trip.yaml"
    dump(original, out)
    reloaded = load(out)
    assert isinstance(reloaded, Map)
    assert reloaded == original


def test_dump_omits_none_provenance(tmp_path: Path) -> None:
    """Optional ``surveyed_at``/``surveyed_by`` are omitted when ``None``.

    Schema v1 does not allow ``null`` for these keys; emitting them with
    ``None`` would produce a file that fails its own validator.
    """
    src = tmp_path / "no_provenance.yaml"
    src.write_text(
        "schema_version: '1.0'\n"
        "warehouse_id: x\n"
        "units: meters\n"
        "coverage_polygon: [[0,0],[10,0],[10,10],[0,10]]\n"
        "takeoff_pad:\n"
        "  position: [1.0, 1.0, 0.0]\n"
        "  yaw_deg: 0\n"
        "  radius_m: 0.5\n"
        "aisles:\n"
        "  - id: A1\n"
        "    centerline: {start: [2,2], end: [2,8]}\n"
        "    width_m: 1.4\n"
        "    direction: any\n"
        "    racks: {}\n"
    )
    m = load(src)
    assert m.surveyed_at is None and m.surveyed_by is None

    out = tmp_path / "dumped.yaml"
    dump(m, out)
    text = out.read_text()
    assert "surveyed_at" not in text
    assert "surveyed_by" not in text
    # Reloading the dumped file must still succeed.
    assert load(out) == m


def test_dump_unwritable_path_raises_map_error(tmp_path: Path) -> None:
    """A bad destination path surfaces as :class:`MapError`, not bare OSError."""
    m = load(REFERENCE_MAP)
    bad = tmp_path / "does_not_exist" / "out.yaml"
    with pytest.raises(MapError, match="cannot write"):
        dump(m, bad)
