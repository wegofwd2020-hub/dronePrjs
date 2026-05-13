"""Cross-domain types shared by every engine sub-package.

These types are the lingua franca between localization, flight_control,
telemetry, and sensors. They must not import from any domain package
(``closedSpace``, ``openSpace``) — see the ISC-36 anti-bleed test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pose:
    """6-DOF drone pose in the map frame.

    Position is meters; ``yaw_deg`` is the absolute heading (0–360).
    ``timestamp_ns`` is a monotonic timestamp from the producer's clock —
    used for staleness checks and log alignment, not as a wall-clock.
    """

    x: float
    y: float
    z: float
    yaw_deg: float
    timestamp_ns: int
