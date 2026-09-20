# ISC-13 Implementation Plan
## Perception-to-command latency p99 < 50 ms over a reference-mission soak

> Status: ready to implement — analysis complete, no code written yet.

---

## The requirement

> "End-to-end perception-to-command latency p99 < 50 ms on the reference
> simulator over a 2-minute soak."

---

## 1. What "perception-to-command" means here

One **cycle** in the runner loop is:

```
t_start ─── SLAM watchdog poll (slam.confidence() — first sensor read)
         ─── link watchdog poll
         ─── abort check
         ─── _execute(wp) → fc.arm / takeoff / goto / land call
t_cmd   (after _execute returns)

latency_ns = t_cmd − t_start
```

The **2-minute soak** in the in-process sim = collecting ≥ 200 samples
(≈ 3 laps of the 70-waypoint reference plan). Wall-clock this takes
milliseconds; the instrumentation infrastructure is the deliverable —
it runs unchanged under Gazebo (Phase 3) where latency will be real.

Cycles that break early (watchdog fires, abort) do **not** record a
sample — `stop()` is only called after `_execute()` completes.

---

## 2. Files that need to change

| File | Change |
|------|--------|
| `closedSpace/constants.py` | Add `PERCEPTION_CMD_LATENCY_P99_S = 0.050` |
| **New** `closedSpace/control/latency.py` | `LatencyRecorder` class |
| `closedSpace/control/__init__.py` | Re-export `LatencyRecorder`; update module docstring |
| `closedSpace/operator/runner.py` | Accept optional `recorder: LatencyRecorder`; call `start()/stop()` around the waypoint loop body; publish `control.latency` bus event |
| **New** `closedSpace/tests/control/test_latency_soak.py` | 6 assertions |

No engine changes — no new Protocols. Timing uses `time.monotonic_ns`
already available in the sim clock chain.

---

## 3. LatencyRecorder design

```python
# closedSpace/control/latency.py

import statistics
import time
from typing import Callable


class LatencyRecorder:
    """Records per-waypoint perception-to-command latency samples.

    Thread-safety: single-threaded, driven synchronously by runner.
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
```

---

## 4. Runner changes — exact insertion points

Current loop structure (runner.py lines 114–143):

```python
for i, wp in enumerate(self._plan.waypoints):
    if self._watchdog ...   # ISC-12
    if self._link_watchdog ...   # ISC-15
    if self._abort ...
    self._execute(wp, ...)
    self._publish_progress(...)
```

New structure after ISC-13:

```python
for i, wp in enumerate(self._plan.waypoints):
    if self._recorder is not None:          # ← NEW: start of perception phase
        self._recorder.start()

    if self._watchdog is not None and self._watchdog.poll():
        aborted = True
        abort_reason = self._watchdog.last_reason
        self._handle_abort()
        break
    if self._link_watchdog is not None and self._link_watchdog.poll():
        aborted = True
        abort_reason = self._link_watchdog.last_reason
        break
    if self._abort.is_set():
        aborted = True
        abort_reason = self._abort.reason
        self._handle_abort()
        break

    self._execute(wp, takeoff_height_m=self._plan.waypoints[0].z)

    if self._recorder is not None:          # ← NEW: command issued
        self._recorder.stop()
        self._publish_latency(self._recorder.samples[-1])

    self._publish_progress(...)
```

New private method on `MissionRunner`:

```python
def _publish_latency(self, latency_ns: int) -> None:
    """Publish one control.latency sample to the telemetry bus."""
    if self._bus is None:
        return
    self._bus.publish(
        "control.latency",
        {
            "topic": "control.latency",
            "timestamp_ns": int(self._clock().timestamp() * 1_000_000_000),
            "payload": {"latency_ns": latency_ns},
        },
    )
```

`MissionRunner.__init__` gains one new optional parameter:

```python
recorder: LatencyRecorder | None = None,
```

---

## 5. Soak test design

Three successive `MissionRunner` laps share one `LatencyRecorder`:

```python
# One recorder, three laps = ≥ 210 samples
recorder = LatencyRecorder()
for _ in range(3):
    runner = MissionRunner(..., recorder=recorder)
    runner.run()

assert len(recorder.samples) >= 200
assert recorder.p99_s() < PERCEPTION_CMD_LATENCY_P99_S
```

Each lap requires a fresh `SimFlightController` (state resets to DISARMED)
but can share the same `SimWorld`, `SimSLAM`, `SimCamera`, `CaptureSink`, and
`ReportBuilder` instances — or fresh ones per lap to keep test state clean.
Use fresh instances per lap for simplicity; the recorder accumulates across all three.

---

## 6. Test assertions

File: `closedSpace/tests/control/test_latency_soak.py`

| # | Test | Assert |
|---|------|--------|
| 1 | Soak passes p99 | 3 laps of reference plan → ≥ 200 samples; p99 < 50 ms |
| 2 | Sample count | completed waypoints == `len(recorder.samples)` (no over- or under-count) |
| 3 | Latency event published | `control.latency` bus event present per completed waypoint; payload has `latency_ns` |
| 4 | Recorder optional | runner with `recorder=None` (default) runs full mission without error |
| 5 | p99 formula correct | fake clock advancing fixed `K` ns each step → all samples == K → `p99_ns() == K` |
| 6 | Empty recorder raises | `p99_ns()` with zero samples raises `statistics.StatisticsError` |

---

## 7. Edge cases

| Case | Handling |
|------|----------|
| Watchdog fires mid-soak | `stop()` not called; `pending_ns` overwritten on next `start()` — no double-count |
| Abort fires | Same — aborted iteration leaves no sample |
| `bus=None` | `_publish_latency` is a no-op; recorder still collects samples |
| `start()` called twice | Second call overwrites `pending_ns` — last-write wins, no double-count |
| All laps abort immediately | `len(recorder.samples) == 0`; soak test would fail — that failure reveals the abort, which is correct |
| Fake-clock soak (test 5) | Use `_FakeClock` advancing by fixed ns per `stop()` call; same pattern as ISC-12/15 tests |

---

## 8. OpenCode prompt to start implementation

Paste this into OpenCode **Build** mode:

```
I'm implementing ISC-13 in the closedSpace sub-project of dronePrjs.
The full plan is in closedSpace/docs/isc-13-implementation-plan.md — read it first.
Also read the finished ISC-12 and ISC-15 code for pattern consistency
(closedSpace/control/watchdog.py, closedSpace/control/link_watchdog.py,
their tests, and closedSpace/operator/runner.py).

Implement in this order:
1. Add PERCEPTION_CMD_LATENCY_P99_S = 0.050 to closedSpace/constants.py
2. Create closedSpace/control/latency.py with LatencyRecorder (exactly as
   specified in §3 of the plan, including the StatisticsError on empty samples)
3. Update closedSpace/control/__init__.py to re-export LatencyRecorder and
   add it to __all__; update the module docstring to mention ISC-13
4. Update closedSpace/operator/runner.py:
   - import LatencyRecorder
   - add optional recorder parameter to __init__
   - insert recorder.start() at the top of the waypoint for-loop (before any
     watchdog check), and recorder.stop() + _publish_latency() immediately
     after _execute() returns (only on the non-break path)
   - add _publish_latency(latency_ns) private method that publishes to
     "control.latency" topic on self._bus
5. Write closedSpace/tests/control/test_latency_soak.py covering all 6
   assertions in §6; the soak test (assertion 1) must run 3 laps of the
   real reference plan using the reference_warehouse.yaml fixture so that
   ≥ 200 samples are collected

No engine changes needed. Run pytest after each file to catch regressions early.
```
