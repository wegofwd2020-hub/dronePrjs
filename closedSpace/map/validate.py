"""Schema and semantic validation for warehouse maps.

Two validation layers run in sequence inside :func:`validate`:

1. **Structural** — JSON Schema (``schemas/map.schema.json``) checks
   field presence, types, enums, and basic numeric ranges.
2. **Semantic** — geometry and consistency rules JSON Schema cannot
   express: polygon simplicity, takeoff pad inside coverage polygon,
   aisle width vs clearance budget, rack extent inside centerline,
   centerline not crossing a no-go zone, id uniqueness, level-index
   monotonicity.

Failures raise :class:`MapValidationError` (semantic and most schema
violations) or :class:`UnsupportedMapVersionError` (version mismatch).
:class:`MapError` is the base class.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import jsonschema

from closedSpace.constants import (
    DRONE_ENVELOPE_M,
    MIN_CLEARANCE_M,
    SUPPORTED_MAP_VERSIONS,
)

#: Path to the JSON Schema bundled with this package.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "map.schema.json"


class MapError(Exception):
    """Base class for all map-loading and -validation errors."""


class MapValidationError(MapError):
    """Map failed structural or semantic validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class UnsupportedMapVersionError(MapError):
    """Map declares a ``schema_version`` this codebase does not support."""

    def __init__(self, version: str) -> None:
        supported = ", ".join(sorted(SUPPORTED_MAP_VERSIONS))
        super().__init__(
            f"schema_version {version!r} is not supported "
            f"(supported: {supported})"
        )
        self.version = version


def load_schema() -> dict[str, Any]:
    """Read the JSON Schema bundled at ``schemas/map.schema.json``.

    Raises:
        MapError: If the schema file is missing or unparseable. This is
            a packaging error, not user input — surfacing it as
            :class:`MapError` lets callers handle "map cannot be
            validated at all" alongside "map is invalid".
    """
    try:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except FileNotFoundError as e:
        raise MapError(f"map.schema.json not found at {_SCHEMA_PATH}") from e
    except json.JSONDecodeError as e:
        raise MapError(f"map.schema.json is not valid JSON: {e}") from e


def validate(data: dict[str, Any]) -> None:
    """Run structural and semantic validation against a parsed map.

    The map is checked in three passes: version, schema, semantics. Each
    pass raises on first failure; subsequent passes are skipped.

    Args:
        data: Parsed map as produced by ``yaml.safe_load``. Not modified.

    Raises:
        UnsupportedMapVersionError: ``schema_version`` not in supported set.
        MapValidationError: Structural or semantic violation.
        MapError: Bundled schema cannot be loaded (programming error).
    """
    _check_version(data)
    _check_schema(data)
    _check_semantics(data)


def _check_version(data: dict[str, Any]) -> None:
    """Reject unsupported ``schema_version`` before schema validation."""
    version = data.get("schema_version")
    if not isinstance(version, str):
        raise MapValidationError(
            "schema_version is missing or not a string",
            field="schema_version",
        )
    if version not in SUPPORTED_MAP_VERSIONS:
        raise UnsupportedMapVersionError(version)


def _check_schema(data: dict[str, Any]) -> None:
    """Run JSON Schema validation; translate to :class:`MapValidationError`."""
    schema = load_schema()
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        field = ".".join(str(p) for p in e.absolute_path) or None
        raise MapValidationError(
            f"schema validation failed: {e.message}",
            field=field,
        ) from e


def _check_semantics(data: dict[str, Any]) -> None:
    """Run all semantic checks; raise on first failure."""
    _check_polygon_simple(data["coverage_polygon"], where="coverage_polygon")

    pad_xy = (
        float(data["takeoff_pad"]["position"][0]),
        float(data["takeoff_pad"]["position"][1]),
    )
    if not _point_in_polygon(pad_xy, data["coverage_polygon"]):
        raise MapValidationError(
            f"takeoff_pad.position {pad_xy} is outside coverage_polygon",
            field="takeoff_pad.position",
        )

    no_go = data.get("no_go_zones") or []
    zone_ids: set[str] = set()
    for zone in no_go:
        if zone["id"] in zone_ids:
            raise MapValidationError(
                f"duplicate no_go_zone id {zone['id']!r}",
                field="no_go_zones",
            )
        zone_ids.add(zone["id"])
        _check_polygon_simple(
            zone["polygon"], where=f"no_go_zones[{zone['id']}].polygon"
        )
        if zone["z_max"] <= zone["z_min"]:
            raise MapValidationError(
                f"no_go_zone {zone['id']!r}: z_max ({zone['z_max']}) "
                f"must exceed z_min ({zone['z_min']})",
                field=f"no_go_zones[{zone['id']}].z_max",
            )

    aisle_ids: set[str] = set()
    rack_ids: set[str] = set()
    for aisle in data["aisles"]:
        if aisle["id"] in aisle_ids:
            raise MapValidationError(
                f"duplicate aisle id {aisle['id']!r}",
                field=f"aisles[{aisle['id']}].id",
            )
        aisle_ids.add(aisle["id"])
        _check_aisle(aisle, data["coverage_polygon"], no_go, rack_ids)


def _check_aisle(
    aisle: dict[str, Any],
    coverage: list[list[float]],
    no_go_zones: list[dict[str, Any]],
    seen_rack_ids: set[str],
) -> None:
    """Per-aisle semantic checks."""
    aid = aisle["id"]
    cl = aisle["centerline"]
    start = (float(cl["start"][0]), float(cl["start"][1]))
    end = (float(cl["end"][0]), float(cl["end"][1]))

    if not _point_in_polygon(start, coverage):
        raise MapValidationError(
            f"aisle {aid!r} centerline.start {start} outside coverage_polygon",
            field=f"aisles[{aid}].centerline.start",
        )
    if not _point_in_polygon(end, coverage):
        raise MapValidationError(
            f"aisle {aid!r} centerline.end {end} outside coverage_polygon",
            field=f"aisles[{aid}].centerline.end",
        )

    min_width = 2 * MIN_CLEARANCE_M + DRONE_ENVELOPE_M
    if aisle["width_m"] < min_width:
        raise MapValidationError(
            f"aisle {aid!r} width_m {aisle['width_m']} < required minimum "
            f"{min_width} (2 × MIN_CLEARANCE_M + DRONE_ENVELOPE_M)",
            field=f"aisles[{aid}].width_m",
        )

    for zone in no_go_zones:
        if _segment_crosses_polygon(start, end, zone["polygon"]):
            raise MapValidationError(
                f"aisle {aid!r} centerline passes through "
                f"no_go_zone {zone['id']!r}",
                field=f"aisles[{aid}].centerline",
            )

    centerline_length = _distance(start, end)
    for side, racks in (aisle.get("racks") or {}).items():
        for rack in (racks or []):
            rid = rack["id"]
            if rid in seen_rack_ids:
                raise MapValidationError(
                    f"duplicate rack id {rid!r}",
                    field=f"aisles[{aid}].racks[{side}][{rid}].id",
                )
            seen_rack_ids.add(rid)

            if rack["face_offset_m"] < MIN_CLEARANCE_M:
                raise MapValidationError(
                    f"rack {rid!r} face_offset_m {rack['face_offset_m']} "
                    f"< MIN_CLEARANCE_M {MIN_CLEARANCE_M}",
                    field=f"aisles[{aid}].racks[{side}][{rid}].face_offset_m",
                )

            half_len = rack["length_m"] / 2.0
            lo = rack["position_along"] - half_len
            hi = rack["position_along"] + half_len
            if lo < 0.0 or hi > centerline_length + 1e-9:
                raise MapValidationError(
                    f"rack {rid!r} extends outside centerline "
                    f"(position_along={rack['position_along']}, "
                    f"length_m={rack['length_m']}, "
                    f"centerline_length={centerline_length:.3f})",
                    field=f"aisles[{aid}].racks[{side}][{rid}].position_along",
                )

            indices = [int(lvl["index"]) for lvl in rack["levels"]]
            if indices != list(range(len(indices))):
                raise MapValidationError(
                    f"rack {rid!r} level indices must be 0..N-1 in order; "
                    f"got {indices}",
                    field=f"aisles[{aid}].racks[{side}][{rid}].levels",
                )


# ---------------------------------------------------------------------------
# Geometry helpers — dependency-free and intentionally simple.
# ---------------------------------------------------------------------------


def _distance(p: tuple[float, float], q: tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _check_polygon_simple(polygon: list[list[float]], *, where: str) -> None:
    """Raise if the polygon is self-intersecting (non-simple)."""
    n = len(polygon)
    if n < 3:
        raise MapValidationError(
            f"polygon at {where} has < 3 vertices", field=where
        )
    edges = [
        (
            (polygon[i][0], polygon[i][1]),
            (polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]),
        )
        for i in range(n)
    ]
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) == 1 or abs(i - j) == n - 1:
                continue  # adjacent edges share an endpoint
            if _segments_intersect(*edges[i], *edges[j]):
                raise MapValidationError(
                    f"polygon at {where} is self-intersecting "
                    f"at edges {i} and {j}",
                    field=where,
                )


def _point_in_polygon(
    p: tuple[float, float], polygon: list[list[float]]
) -> bool:
    """Ray-casting point-in-polygon (boundary points count as inside).

    Uses the standard horizontal-ray algorithm with a tiny epsilon to
    avoid divide-by-zero on horizontal edges.
    """
    x, y = p
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        crosses = (yi > y) != (yj > y)
        if crosses:
            x_intersect = (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
            if x <= x_intersect:
                inside = not inside
        j = i
    return inside


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Proper segment-segment intersection (collinear overlaps return False)."""

    def ccw(
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
    ) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _segment_crosses_polygon(
    p1: tuple[float, float],
    p2: tuple[float, float],
    polygon: list[list[float]],
) -> bool:
    """``True`` iff segment ``p1-p2`` crosses any polygon edge OR an
    endpoint lies strictly inside the polygon.

    Used to decide whether an aisle centerline passes through a no-go zone.
    """
    if _point_in_polygon(p1, polygon) or _point_in_polygon(p2, polygon):
        return True
    n = len(polygon)
    for i in range(n):
        e1 = (polygon[i][0], polygon[i][1])
        e2 = (polygon[(i + 1) % n][0], polygon[(i + 1) % n][1])
        if _segments_intersect(p1, p2, e1, e2):
            return True
    return False
