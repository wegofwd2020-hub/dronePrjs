"""ISC-13 LatencyRecorder — per-waypoint perception-to-command timing.

:class:`LatencyRecorder` brackets the start of the perception phase
(top of the waypoint loop, before any watchdog check) and the end of
the command phase (after :meth:`MissionRunner._execute` returns).
The mission runner calls :meth:`start` / :meth:`stop` synchronously;
this class performs no I/O and must be single-threaded.

Design notes:
* :meth:`start` overwrites any un-stopped pending mark — aborted
  cycles (watchdog / abort break) leave no sample.
* :meth:`stop` is a no-op if :meth:`start` was never called.
* :meth:`p99_ns` uses ``sorted[floor(0.99 * n)]`` (index method).
"""
from __future__ import annotations

import statistics
import time
from typing import Callable

__all__ = ["LatencyRecorder"]


class LatencyRecorder:
    """Records per-waypoint perception-to-command latency samples.

    Thread-safety: single-threaded, driven synchronously by the runner.
    """

    def __init__(self, clock: Callable[[], int] | None = None) -> None:
        self._clock = clock or time.monotonic_ns
        self._samples_ns: list[int] = []
        self._pending_ns: int | None = None

    def start(self) -> None:
        """Mark start of perception phase (top of waypoint loop).

        Overwrites any un-stopped pending mark — handles aborted cycles
        cleanly without raising.
        """
        self._pending_ns = self._clock()

    def stop(self) -> None:
        """Mark end of command phase (after _execute returns).

        Records elapsed ns. No-op if start() was never called.
        """
        if self._pending_ns is not None:
            self._samples_ns.append(self._clock() - self._pending_ns)
            self._pending_ns = None

    @property
    def samples(self) -> list[int]:
        """All recorded latency samples in ns, in arrival order."""
        return list(self._samples_ns)

    def p99_ns(self) -> int:
        """99th-percentile latency in nanoseconds.

        Uses the index method: sorted[floor(0.99 * n)].
        Raises StatisticsError when no samples recorded.
        """
        if not self._samples_ns:
            raise statistics.StatisticsError("no latency samples recorded")
        s = sorted(self._samples_ns)
        idx = int(0.99 * len(s))
        return s[idx]

    def p99_s(self) -> float:
        """99th-percentile latency in seconds."""
        return self.p99_ns() / 1_000_000_000
