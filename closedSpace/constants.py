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

#: SLAM tracking confidence below this → drop to ``SAFE_HOVER`` (ISC-12).
#: Strict `<`: exactly at threshold still counts as tracking.
SLAM_CONFIDENCE_THRESHOLD: float = 0.5

#: Sleep between watchdog polls of SLAM confidence (s). Must stay well
#: under :data:`SAFE_HOVER_MAX_LATENCY_S` so a loss is caught in budget.
SLAM_POLL_INTERVAL_S: float = 0.02

#: Worst-case budget from first SLAM-loss observation to ``SAFE_HOVER``
#: entry (s). ISC-12 mandates ≤ 200 ms; poll cadence must keep slack.
SAFE_HOVER_MAX_LATENCY_S: float = 0.2

#: Ground-station silence beyond this → return-to-home + land (ISC-15).
#: Strict `>`: exactly at the timeout still counts as connected.
LINK_LOSS_TIMEOUT_S: float = 5.0

#: Bed between link-loss watchdog polls (s). Must be ≤ timeout / 2 so at
#: least two polls fit inside the timeout window.
LINK_POLL_INTERVAL_S: float = 0.5
