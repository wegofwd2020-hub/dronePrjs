"""Typed :class:`closedSpace.map.types.Map` → YAML file.

The single public entry point is :func:`dump`. It serializes a Map to
YAML that round-trips through :func:`closedSpace.map.loader.load` — the
property ISC-5 asserts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from closedSpace.map.types import Aisle, Map, NoGoZone, Rack, TakeoffPad
from closedSpace.map.validate import MapError


def dump(m: Map, path: str | Path) -> None:
    """Serialize a Map to a YAML file.

    The output is guaranteed to parse back to an equal :class:`Map` via
    :func:`closedSpace.map.loader.load`. Optional provenance fields
    (``surveyed_at``, ``surveyed_by``) are omitted when ``None`` so we
    don't emit ``key: null`` lines that schema v1 doesn't define.

    Args:
        m: A Map instance, typically produced by :func:`load`.
        path: Destination filesystem path. Parent directory must exist.

    Raises:
        MapError: Destination cannot be opened for writing.
    """
    data = _map_to_dict(m)
    p = Path(path)
    try:
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
    except OSError as e:
        raise MapError(f"cannot write map to {p}: {e}") from e


def _map_to_dict(m: Map) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": m.schema_version,
        "warehouse_id": m.warehouse_id,
        "units": m.units,
    }
    if m.surveyed_at is not None:
        out["surveyed_at"] = m.surveyed_at
    if m.surveyed_by is not None:
        out["surveyed_by"] = m.surveyed_by
    out["coverage_polygon"] = [[p.x, p.y] for p in m.coverage_polygon]
    out["takeoff_pad"] = _takeoff_pad_to_dict(m.takeoff_pad)
    out["no_go_zones"] = [_no_go_zone_to_dict(z) for z in m.no_go_zones]
    out["aisles"] = [_aisle_to_dict(a) for a in m.aisles]
    return out


def _takeoff_pad_to_dict(pad: TakeoffPad) -> dict[str, Any]:
    return {
        "position": [pad.position.x, pad.position.y, pad.position.z],
        "yaw_deg": pad.yaw_deg,
        "radius_m": pad.radius_m,
    }


def _no_go_zone_to_dict(z: NoGoZone) -> dict[str, Any]:
    return {
        "id": z.id,
        "polygon": [[p.x, p.y] for p in z.polygon],
        "z_min": z.z_min,
        "z_max": z.z_max,
    }


def _aisle_to_dict(a: Aisle) -> dict[str, Any]:
    return {
        "id": a.id,
        "centerline": {
            "start": [a.centerline.start.x, a.centerline.start.y],
            "end": [a.centerline.end.x, a.centerline.end.y],
        },
        "width_m": a.width_m,
        "direction": a.direction,
        "racks": {side: [_rack_to_dict(r) for r in racks] for side, racks in a.racks.items()},
    }


def _rack_to_dict(r: Rack) -> dict[str, Any]:
    return {
        "id": r.id,
        "position_along": r.position_along,
        "length_m": r.length_m,
        "face_offset_m": r.face_offset_m,
        "yaw_deg": r.yaw_deg,
        "levels": [{"index": lvl.index, "height_m": lvl.height_m} for lvl in r.levels],
    }
