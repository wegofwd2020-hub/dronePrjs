"""Tests for :mod:`closedSpace.map.validate` semantic rules.

Each test mutates a fresh deep copy of the reference fixture in exactly
one way and asserts the validator catches it. This isolates per-rule
behavior and keeps failures actionable.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from closedSpace.map.validate import (
    MapValidationError,
    UnsupportedMapVersionError,
    validate,
)

REFERENCE_MAP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "maps"
    / "reference_warehouse.yaml"
)


@pytest.fixture
def ref_data() -> dict:
    """Fresh deep copy of the reference fixture for each test."""
    with open(REFERENCE_MAP, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_reference_passes(ref_data: dict) -> None:
    """ISC-1 antecedent: reference fixture must validate."""
    validate(ref_data)


def test_unsupported_version_rejected(ref_data: dict) -> None:
    ref_data["schema_version"] = "0.9"
    with pytest.raises(UnsupportedMapVersionError):
        validate(ref_data)


def test_missing_units_rejected(ref_data: dict) -> None:
    del ref_data["units"]
    with pytest.raises(MapValidationError):
        validate(ref_data)


def test_takeoff_outside_coverage_rejected(ref_data: dict) -> None:
    """Takeoff pad outside the [0..12, 0..8] coverage is rejected."""
    ref_data["takeoff_pad"]["position"] = [-1.0, -1.0, 0.0]
    with pytest.raises(MapValidationError, match="outside coverage_polygon"):
        validate(ref_data)


def test_aisle_too_narrow_rejected(ref_data: dict) -> None:
    """Aisle width below 2 × MIN_CLEARANCE_M + DRONE_ENVELOPE_M is rejected."""
    ref_data["aisles"][0]["width_m"] = 1.0  # below 1.4 minimum
    with pytest.raises(MapValidationError, match="width_m"):
        validate(ref_data)


def test_face_offset_below_clearance_rejected(ref_data: dict) -> None:
    """A rack with ``face_offset_m`` < MIN_CLEARANCE_M is rejected."""
    ref_data["aisles"][0]["racks"]["west"][0]["face_offset_m"] = 0.3
    with pytest.raises(MapValidationError, match="face_offset_m"):
        validate(ref_data)


def test_rack_overshoot_rejected(ref_data: dict) -> None:
    """A rack whose extent runs past centerline length is rejected."""
    # Centerline length = 5.0; pushing position_along to 4.9 with length 1.2
    # makes the rack extend to 5.5, past the centerline.
    ref_data["aisles"][0]["racks"]["west"][0]["position_along"] = 4.9
    with pytest.raises(MapValidationError, match="outside centerline"):
        validate(ref_data)


def test_duplicate_aisle_id_rejected(ref_data: dict) -> None:
    ref_data["aisles"][1]["id"] = "A1"
    with pytest.raises(MapValidationError, match="duplicate aisle id"):
        validate(ref_data)


def test_duplicate_rack_id_rejected(ref_data: dict) -> None:
    ref_data["aisles"][0]["racks"]["west"][1]["id"] = "A1-W1"
    with pytest.raises(MapValidationError, match="duplicate rack id"):
        validate(ref_data)


def test_no_go_polygon_with_two_vertices_rejected(ref_data: dict) -> None:
    """Polygon with < 3 vertices — schema layer catches this."""
    ref_data["no_go_zones"][0]["polygon"] = [[0.0, 0.0], [1.0, 0.0]]
    with pytest.raises(MapValidationError):
        validate(ref_data)


def test_centerline_through_no_go_rejected(ref_data: dict) -> None:
    """A no-go zone planted on aisle A1's centerline (x=3.0) is rejected."""
    ref_data["no_go_zones"].append(
        {
            "id": "blocker",
            "polygon": [
                [2.9, 3.5],
                [3.1, 3.5],
                [3.1, 3.7],
                [2.9, 3.7],
            ],
            "z_min": 0.0,
            "z_max": 5.0,
        }
    )
    with pytest.raises(MapValidationError, match="passes through no_go_zone"):
        validate(ref_data)


def test_level_indices_must_be_sequential(ref_data: dict) -> None:
    """Level indices must be 0..N-1; gaps or out-of-order are rejected."""
    ref_data["aisles"][0]["racks"]["west"][0]["levels"] = [
        {"index": 0, "height_m": 0.5},
        {"index": 2, "height_m": 1.5},  # skipped 1
    ]
    with pytest.raises(MapValidationError, match="level indices"):
        validate(ref_data)


def test_duplicate_no_go_zone_id_rejected(ref_data: dict) -> None:
    """Two no-go zones with the same id are rejected."""
    ref_data["no_go_zones"].append(dict(ref_data["no_go_zones"][0]))
    with pytest.raises(MapValidationError, match="duplicate no_go_zone id"):
        validate(ref_data)
