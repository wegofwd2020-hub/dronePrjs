"""Unit tests for :class:`closedSpace.control.LatencyRecorder`.

Covers the pure-class behaviour of LatencyRecorder in isolation
(no MissionRunner, no filesystem).  Integration / soak tests that
exercise the runner wiring live in test_latency_soak.py.
"""
from __future__ import annotations

import statistics

import pytest

from closedSpace.control import LatencyRecorder


# ---------------------------------------------------------------------------
# p99 formula — fixed-step clock → every sample == K → p99_ns() == K
# ---------------------------------------------------------------------------


def test_p99_formula_fixed_step_clock() -> None:
    K = 12_345_678  # ns — arbitrary fixed step
    calls = [0]

    def step_clock() -> int:
        t = calls[0] * K
        calls[0] += 1
        return t

    recorder = LatencyRecorder(clock=step_clock)
    for _ in range(10):
        recorder.start()  # returns 0, 2K, 4K, …
        recorder.stop()   # returns K, 3K, 5K, … → elapsed = K each time

    assert all(s == K for s in recorder.samples)
    assert recorder.p99_ns() == K


# ---------------------------------------------------------------------------
# p99_s — returns seconds equivalent
# ---------------------------------------------------------------------------


def test_p99_s_converts_to_seconds() -> None:
    calls = [0]

    def step_clock() -> int:
        t = calls[0]
        calls[0] += 1_000_000  # 1 ms per call pair
        return t

    recorder = LatencyRecorder(clock=step_clock)
    recorder.start()
    recorder.stop()
    assert recorder.p99_s() == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# Empty recorder raises StatisticsError
# ---------------------------------------------------------------------------


def test_p99_raises_on_empty_recorder() -> None:
    recorder = LatencyRecorder()
    with pytest.raises(statistics.StatisticsError):
        recorder.p99_ns()


# ---------------------------------------------------------------------------
# start() called twice — last-write wins, no double sample
# ---------------------------------------------------------------------------


def test_double_start_overwrites_pending() -> None:
    t = [0]

    def clock() -> int:
        t[0] += 1
        return t[0]

    recorder = LatencyRecorder(clock=clock)
    recorder.start()   # pending_ns = 1
    recorder.start()   # pending_ns = 2 (overwrites)
    recorder.stop()    # elapsed = 3 - 2 = 1

    assert len(recorder.samples) == 1
    assert recorder.samples[0] == 1


# ---------------------------------------------------------------------------
# stop() without start() is a no-op
# ---------------------------------------------------------------------------


def test_stop_without_start_is_noop() -> None:
    recorder = LatencyRecorder()
    recorder.stop()  # must not raise
    assert recorder.samples == []
