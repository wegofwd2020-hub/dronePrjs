"""closedSpace.mission — pure Map → MissionPlan planning.

Public surface:

* :func:`plan` — derive a MissionPlan from a Map (and optional config).
* :class:`MissionPlan`, :class:`Waypoint`, :class:`MissionConfig` —
  typed mission structures.
* :class:`TransitBlockedError` — raised when v1 naive routing can't
  produce a no-go-zone-free path.

Spec: ``closedSpace/docs/map-schema.md`` §10.
"""
from __future__ import annotations

from closedSpace.mission.plan import plan
from closedSpace.mission.transit import TransitBlockedError
from closedSpace.mission.types import MissionConfig, MissionPlan, Waypoint

__all__ = [
    "MissionConfig",
    "MissionPlan",
    "TransitBlockedError",
    "Waypoint",
    "plan",
]
