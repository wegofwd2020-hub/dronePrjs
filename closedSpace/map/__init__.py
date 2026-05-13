"""closedSpace.map — Warehouse map loading and validation.

Public surface:

* :func:`load` — read a YAML map and return a validated :class:`Map`.
* :class:`Map`, :class:`Aisle`, :class:`Rack`, :class:`Level`,
  :class:`NoGoZone`, :class:`TakeoffPad`, :class:`Point2D`,
  :class:`Point3D`, :class:`Centerline` — typed map structures.
* :class:`MapError`, :class:`MapValidationError`,
  :class:`UnsupportedMapVersionError` — exceptions.
"""
from __future__ import annotations

from closedSpace.map.loader import load
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
from closedSpace.map.validate import (
    MapError,
    MapValidationError,
    UnsupportedMapVersionError,
)

__all__ = [
    "Aisle",
    "Centerline",
    "Level",
    "Map",
    "MapError",
    "MapValidationError",
    "NoGoZone",
    "Point2D",
    "Point3D",
    "Rack",
    "TakeoffPad",
    "UnsupportedMapVersionError",
    "load",
]
