"""engine.localization — position estimation providers.

Two Protocols, one per domain:

* :class:`SLAMProvider` — visual-inertial odometry; required for closedSpace.
* :class:`GPSProvider` — GPS + IMU fusion; required for openSpace.

Both implement :class:`PositionProvider` so generic engine code can hold
either. **Domain rule (ISC-30):** ``closedSpace`` MUST NOT import
``GPSProvider``. The anti-bleed test in ``engine/tests/`` scans for
violations.

Lifecycle: ``start()`` arms the underlying tracker; ``stop()`` releases
resources. ``get_pose()`` is the hot-loop call and must be non-blocking;
``confidence()`` lets the flight controller's safety state machine
decide when to drop to ``SAFE_HOVER`` (ISC-12).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from engine.types import Pose


@runtime_checkable
class PositionProvider(Protocol):
    """Common surface for any position estimator.

    Concrete providers MUST satisfy this Protocol structurally; explicit
    inheritance is not required. Use :func:`isinstance` checks against
    this Protocol for runtime conformance tests.
    """

    def start(self) -> None:
        """Begin pose estimation. Idempotent — re-start is a no-op."""
        ...

    def stop(self) -> None:
        """Halt estimation and release resources. Safe to call twice."""
        ...

    def get_pose(self) -> Pose:
        """Return the latest pose. Non-blocking; raises if not started."""
        ...

    def confidence(self) -> float:
        """Estimator confidence in ``[0.0, 1.0]``. Below the platform's
        threshold, the flight controller transitions to ``SAFE_HOVER``.
        """
        ...


@runtime_checkable
class SLAMProvider(PositionProvider, Protocol):
    """Visual-inertial / fiducial-fused SLAM. closedSpace-only.

    Implementations may add stack-specific extras (loop-closure events,
    map persistence, fiducial-detection hooks); only the
    :class:`PositionProvider` surface is the cross-domain contract.
    """


@runtime_checkable
class GPSProvider(PositionProvider, Protocol):
    """GPS + IMU fusion. openSpace-only. **Forbidden in closedSpace.**

    The anti-bleed test grep-checks ``closedSpace/`` for imports of this
    name; any hit fails CI.
    """


__all__ = ["GPSProvider", "PositionProvider", "SLAMProvider"]
