"""Typed structures for mission plans.

The :func:`closedSpace.mission.plan.plan` function consumes a
:class:`~closedSpace.map.types.Map` plus a :class:`MissionConfig` and
returns a :class:`MissionPlan` — an ordered, immutable sequence of
:class:`Waypoint` objects plus aggregate metrics.

Format spec: ``closedSpace/docs/map-schema.md`` §10 (path-derivation
contract). Field defaults in :class:`MissionConfig` come from §10.3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

#: Waypoint metadata kind for non-capture waypoints. Capture waypoints
#: use ``"capture"`` and carry ``aisle_id``/``rack_id``/``level_index``.
WaypointKind = Literal["takeoff", "transit", "capture", "landing"]


@dataclass(frozen=True, slots=True)
class Waypoint:
    """One discrete drone pose along the mission.

    A capture waypoint pauses for ``MissionConfig.capture_dwell_s`` and
    triggers the camera. Non-capture waypoints (takeoff, transit,
    landing) are flown through without dwell.

    ``metadata`` keys depend on ``kind``:

    * ``kind == "capture"``: ``{aisle_id, rack_id, level_index}``
    * ``kind == "takeoff" | "transit" | "landing"``: empty or freeform
    """

    x: float
    y: float
    z: float
    yaw_deg: float
    kind: WaypointKind
    metadata: Mapping[str, str | int] = field(default_factory=dict)

    @property
    def capture(self) -> bool:
        """Convenience predicate matching the §10.1 ``capture`` flag."""
        return self.kind == "capture"


@dataclass(frozen=True, slots=True)
class MissionConfig:
    """Per-mission tunables — see ``docs/map-schema.md`` §10.3.

    Defaults are the spec values; all are overridable per mission. None
    of these belong in the map; the map is geometry, this is policy.
    """

    takeoff_height_m: float = 1.5
    aisle_traversal_height_m: float = 1.0
    max_mission_duration_s: float = 900.0
    nominal_speed_mps: float = 1.0
    capture_dwell_s: float = 3.0


@dataclass(frozen=True, slots=True)
class MissionPlan:
    """An immutable, deterministic mission plan.

    ``waypoints`` is the full ordered sequence; ``capture_count`` is the
    number of capture waypoints (a derived field stored eagerly so test
    probes don't have to re-walk the list). ``path_length_m`` is the
    summed Euclidean length of the polyline; ``est_duration_s`` is the
    planner's coarse duration estimate used for the ISC-8 gate.
    """

    waypoints: tuple[Waypoint, ...]
    path_length_m: float
    est_duration_s: float
    capture_count: int
