"""Typed structures for parsed warehouse maps.

These dataclasses are the in-memory representation of a parsed and
validated map. They are frozen — once a :class:`Map` is loaded, it is
immutable for the lifetime of the mission.

Format spec: ``closedSpace/docs/map-schema.md``.
JSON Schema: ``closedSpace/schemas/map.schema.json``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

#: Allowed values for :attr:`Aisle.direction`. ``"any"`` lets the planner
#: choose the entry end (boustrophedon by default).
Direction = Literal[
    "any",
    "north_to_south",
    "south_to_north",
    "east_to_west",
    "west_to_east",
]

#: Side names valid inside :attr:`Aisle.racks`. ``west``/``east`` for
#: north-south aisles, ``north``/``south`` for east-west aisles.
SideName = Literal["west", "east", "north", "south"]


@dataclass(frozen=True, slots=True)
class Point2D:
    """A 2D point in the map frame (meters)."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Point3D:
    """A 3D point in the map frame (meters)."""

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class TakeoffPad:
    """Where the drone arms, takes off, and lands."""

    position: Point3D
    yaw_deg: float
    radius_m: float


@dataclass(frozen=True, slots=True)
class NoGoZone:
    """A 2D polygon with vertical extent the drone may not enter."""

    id: str
    polygon: tuple[Point2D, ...]
    z_min: float
    z_max: float


@dataclass(frozen=True, slots=True)
class Level:
    """A shelf level on a rack — one capture per ``(rack, level)``."""

    index: int
    height_m: float


@dataclass(frozen=True, slots=True)
class Rack:
    """A rack of shelves on one side of an aisle."""

    id: str
    position_along: float
    length_m: float
    face_offset_m: float
    yaw_deg: float
    levels: tuple[Level, ...]


@dataclass(frozen=True, slots=True)
class Centerline:
    """The line the drone flies along when traversing an aisle."""

    start: Point2D
    end: Point2D


@dataclass(frozen=True, slots=True)
class Aisle:
    """A corridor with shelving on one or both sides."""

    id: str
    centerline: Centerline
    width_m: float
    direction: Direction
    racks: Mapping[SideName, tuple[Rack, ...]]


@dataclass(frozen=True, slots=True)
class Map:
    """A full warehouse structural map.

    The ``surveyed_at`` / ``surveyed_by`` fields are optional in schema
    v1 and may be ``None`` for legacy maps. The mission planner's
    pre-flight gate inspects ``surveyed_at`` to decide whether the map
    is too stale to fly.
    """

    schema_version: str
    warehouse_id: str
    units: str
    coverage_polygon: tuple[Point2D, ...]
    takeoff_pad: TakeoffPad
    no_go_zones: tuple[NoGoZone, ...]
    aisles: tuple[Aisle, ...]
    surveyed_at: str | None = None
    surveyed_by: str | None = None
