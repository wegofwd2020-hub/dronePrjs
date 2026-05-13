"""Flight-platform invariants for closedSpace.

These are intrinsic properties of the drone and its safety envelope. They
do NOT vary per mission. Per-mission tunables (takeoff height, traversal
height, link-loss timeout, etc.) live with the mission planner, not here.
"""
from __future__ import annotations

#: Minimum allowed clearance from any detected surface during flight (m).
#: Hard floor; per the project's safety doctrine, configurable up but
#: never down.
MIN_CLEARANCE_M: float = 0.5

#: Effective horizontal radius of the drone bounding cylinder, including
#: rotor extent (m). Used to bound minimum aisle width.
DRONE_ENVELOPE_M: float = 0.4

#: Set of map ``schema_version`` values this codebase understands.
#: Bumping requires a coordinated change across loader, validator, and
#: any persisted maps.
SUPPORTED_MAP_VERSIONS: frozenset[str] = frozenset({"1.0"})
