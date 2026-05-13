"""YAML → typed :class:`closedSpace.map.types.Map`.

The single public entry point is :func:`load`. It reads a YAML file,
validates it against the v1.0 contract, and returns an immutable
:class:`Map`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from closedSpace.map.types import (
    Aisle,
    Centerline,
    Level,
    Map,
    NoGoZone,
    Point2D,
    Point3D,
    Rack,
    TakeoffPad,
)
from closedSpace.map.validate import MapError, MapValidationError, validate


def load(path: str | Path) -> Map:
    """Load and validate a warehouse map from a YAML file.

    Args:
        path: Filesystem path to a YAML file.

    Returns:
        An immutable :class:`Map`.

    Raises:
        MapError: File not found or YAML unparseable.
        MapValidationError: Map fails structural or semantic validation.
        UnsupportedMapVersionError: ``schema_version`` is not supported.
    """
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise MapError(f"map file not found: {p}") from e
    except yaml.YAMLError as e:
        raise MapError(f"map file is not valid YAML: {p} — {e}") from e

    if not isinstance(data, dict):
        raise MapValidationError(
            f"map root must be a mapping, got {type(data).__name__}",
            field="<root>",
        )

    validate(data)
    return _build_map(data)


def _build_map(data: dict[str, Any]) -> Map:
    """Construct the typed Map from a validated dict."""
    return Map(
        schema_version=data["schema_version"],
        warehouse_id=data["warehouse_id"],
        units=data["units"],
        coverage_polygon=tuple(
            Point2D(p[0], p[1]) for p in data["coverage_polygon"]
        ),
        takeoff_pad=_build_takeoff_pad(data["takeoff_pad"]),
        no_go_zones=tuple(
            _build_no_go_zone(z) for z in (data.get("no_go_zones") or [])
        ),
        aisles=tuple(_build_aisle(a) for a in data["aisles"]),
        surveyed_at=data.get("surveyed_at"),
        surveyed_by=data.get("surveyed_by"),
    )


def _build_takeoff_pad(d: dict[str, Any]) -> TakeoffPad:
    pos = d["position"]
    return TakeoffPad(
        position=Point3D(float(pos[0]), float(pos[1]), float(pos[2])),
        yaw_deg=float(d["yaw_deg"]),
        radius_m=float(d["radius_m"]),
    )


def _build_no_go_zone(d: dict[str, Any]) -> NoGoZone:
    return NoGoZone(
        id=str(d["id"]),
        polygon=tuple(Point2D(float(p[0]), float(p[1])) for p in d["polygon"]),
        z_min=float(d["z_min"]),
        z_max=float(d["z_max"]),
    )


def _build_aisle(d: dict[str, Any]) -> Aisle:
    racks_in = d.get("racks") or {}
    racks_out: dict[str, tuple[Rack, ...]] = {}
    for side, racks in racks_in.items():
        racks_out[side] = tuple(_build_rack(r) for r in (racks or []))
    return Aisle(
        id=str(d["id"]),
        centerline=Centerline(
            start=Point2D(
                float(d["centerline"]["start"][0]),
                float(d["centerline"]["start"][1]),
            ),
            end=Point2D(
                float(d["centerline"]["end"][0]),
                float(d["centerline"]["end"][1]),
            ),
        ),
        width_m=float(d["width_m"]),
        direction=d["direction"],
        racks=racks_out,  # type: ignore[arg-type]
    )


def _build_rack(d: dict[str, Any]) -> Rack:
    return Rack(
        id=str(d["id"]),
        position_along=float(d["position_along"]),
        length_m=float(d["length_m"]),
        face_offset_m=float(d["face_offset_m"]),
        yaw_deg=float(d["yaw_deg"]),
        levels=tuple(
            Level(index=int(lvl["index"]), height_m=float(lvl["height_m"]))
            for lvl in d["levels"]
        ),
    )
