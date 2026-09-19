"""engine.link — ground-station link / keepalive monitoring.

The :class:`LinkMonitor` Protocol is the cross-stack surface for link-loss
detection. The ground station (or its emulator) calls :meth:`heartbeat`
on every keepalive it receives; the flight-side safety watchdog compares
:meth:`last_heartbeat_ns` against the monotonic clock to measure elapsed
silence (ISC-15).

Like every engine Protocol, implementations satisfy it structurally —
explicit inheritance is not required. :func:`isinstance` against this
Protocol works at runtime thanks to ``runtime_checkable``.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LinkMonitor(Protocol):
    """Tracks ground-station keepalive timestamps.

    The ground station calls :meth:`heartbeat` on every keepalive
    received. The watchdog compares :meth:`last_heartbeat_ns` against
    the monotonic clock to determine elapsed silence.
    """

    def heartbeat(self) -> None:
        """Record receipt of a ground-station keepalive. Thread-safe."""
        ...

    def last_heartbeat_ns(self) -> int:
        """Monotonic ns of the most recent heartbeat. Returns 0 if never
        received (treated as maximum elapsed time by the watchdog)."""
        ...


__all__ = ["LinkMonitor"]