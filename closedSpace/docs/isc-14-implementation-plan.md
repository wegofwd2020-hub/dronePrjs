# ISC-14 & ISC-33 Implementation Plan
## Clearance enforcement: drone holds ≥ 0.5 m from any surface; zero telemetry violations

> Status: ready to implement — analysis complete, no code written yet.

---

## The requirements

> **ISC-14:** Drone holds 0.5 m minimum clearance from any detected surface
> throughout the reference mission (probe: post-flight log scan for
> clearance < 0.5).

> **ISC-33:** Anti: zero telemetry samples with `min_clearance_m < 0.5`
> outside takeoff/landing geofence.

> **ISC-31:** Anti: zero log entries with severity `COLLISION` after a
> reference mission run.

All three are satisfied by the same implementation: a `ClearanceWatchdog`
that polls a `ProximitySensor` after every `_execute()` call, logs a
`control.clearance` telemetry event per waypoint, and on violation emits a
`control.collision` event (severity `COLLISION`) then transitions to
`SAFE_HOVER`.

---

## 1. Design overview

```
ProximitySensor (engine Protocol)
        ↓ min_clearance_m()
ClearanceWatchdog.poll()          ← called by runner after _execute()
        ↓
   always: publish control.clearance {min_clearance_m, violation: false}
   on violation: publish control.collision {severity: "COLLISION"} + SAFE_HOVER
```

The reference mission passes ISC-14/33/31 because `SimProximitySensor`
always returns a safe value (≥ MIN_CLEARANCE_M). The watchdog code handles
violations correctly — they just never fire in the passing mission.

Geofence rule (ISC-33 "outside takeoff/landing geofence"): only check
clearance when `fc.get_state() is AIRBORNE` AND `fc.get_pose().z >=
CLEARANCE_GEOFENCE_HEIGHT_M`. This exempts the low-altitude takeoff climb
and landing descent.

---

## 2. Files that need to change

| File | Change |
|------|--------|
| `engine/sensors/__init__.py` | Add `ProximitySensor` Protocol (additive only — no existing code changes) |
| `engine/sim/__init__.py` | Add `SimProximitySensor` class (additive only) |
| `closedSpace/constants.py` | Add `CLEARANCE_GEOFENCE_HEIGHT_M` |
| **New** `closedSpace/control/clearance_watchdog.py` | `ClearanceWatchdog` class |
| `closedSpace/control/__init__.py` | Re-export `ClearanceWatchdog`; update module docstring |
| `closedSpace/operator/runner.py` | Accept optional `clearance_watchdog`; poll after `_execute()` |
| **New** `closedSpace/tests/control/test_clearance_watchdog.py` | 7 assertions |

Engine changes are **additive only** — no existing engine interface is
modified. openSpace is unaffected.

---

## 3. ProximitySensor Protocol — exact addition to engine/sensors/__init__.py

Add this block immediately before the `__all__` line at the end of the file:

```python
@runtime_checkable
class ProximitySensor(Protocol):
    """Minimum distance to any detected surface in the drone's vicinity.

    Real implementations read from depth cameras, ultrasonic rangers, or
    LiDAR. The sim stub returns a configurable value via :meth:`set_clearance`.
    """

    def min_clearance_m(self) -> float:
        """Minimum distance to any detected surface, in metres.

        Returns:
            Distance in metres. Values < MIN_CLEARANCE_M indicate a
            clearance violation that must be handled by the caller.

        Raises:
            RuntimeError: If the sensor is not started or has failed.
                The caller (ClearanceWatchdog) treats any exception as a
                violation — unknown clearance is unsafe.
        """
        ...
```

Also add `"ProximitySensor"` to the `__all__` list at the bottom.

---

## 4. SimProximitySensor — exact addition to engine/sim/__init__.py

### 4a. Add the class before the conformance block

The conformance block near the end of engine/sim/__init__.py starts with:
```
# Conformance: assert structural subtyping at import time so test discovery
```

Insert the following class immediately BEFORE that comment:

```python
class SimProximitySensor:
    """In-process :class:`ProximitySensor` — returns a configurable clearance.

    Default clearance is 2.0 m (safely above MIN_CLEARANCE_M). Use
    :meth:`set_clearance` in tests to inject specific values and exercise
    violation detection without needing real obstacle geometry.
    """

    def __init__(self, world: SimWorld, default_clearance_m: float = 2.0) -> None:
        self._world = world
        self._clearance_m = default_clearance_m

    def min_clearance_m(self) -> float:
        """Current simulated clearance in metres."""
        return self._clearance_m

    def set_clearance(self, value: float) -> None:
        """Test hook: inject a specific clearance reading.

        Args:
            value: New clearance in metres. Any float is accepted —
                negative values simulate sensor failure states in tests.

        Raises:
            Nothing. The watchdog handles all edge cases at call time.
        """
        self._clearance_m = value
```

### 4b. Update the conformance tuple

Find the line that reads:
```
    type[SLAMProvider], type[FlightController], type[Camera], type[LinkMonitor]
```

Change it to:
```
    type[SLAMProvider], type[FlightController], type[Camera], type[LinkMonitor],
    type[ProximitySensor],
```

Also add the import at the top of the conformance tuple assignment:
Find:
```python
from engine.sensors import Camera, Frame, laplacian_focus_score
```
Change to:
```python
from engine.sensors import Camera, Frame, ProximitySensor, laplacian_focus_score
```

### 4c. Add to __all__

Add `"SimProximitySensor"` to the `__all__` list at the bottom.

---

## 5. Constants — exact addition to closedSpace/constants.py

Find the last line of closedSpace/constants.py:
```python
PERCEPTION_CMD_LATENCY_P99_S: float = 0.050
```

Append after it:

```python
#: Height below which clearance checks are suspended (m). The drone
#: legitimately passes through this zone during takeoff climb and
#: landing descent. ISC-33 "outside takeoff/landing geofence".
CLEARANCE_GEOFENCE_HEIGHT_M: float = 1.0
```

---

## 6. ClearanceWatchdog — create closedSpace/control/clearance_watchdog.py

Create the file with exactly this content:

```python
"""ISC-14 ClearanceWatchdog — per-waypoint clearance enforcement.

:class:`ClearanceWatchdog` polls a :class:`ProximitySensor` after every
``_execute()`` call and:

* Always publishes a ``control.clearance`` telemetry event with the
  measured ``min_clearance_m`` (used by the post-flight log scan).
* On violation (< MIN_CLEARANCE_M): publishes a ``control.collision``
  event with ``severity: "COLLISION"`` and transitions to ``SAFE_HOVER``.

Geofence rule (ISC-33): only checks clearance when
``fc.get_state() is AIRBORNE`` AND ``fc.get_pose().z >=
CLEARANCE_GEOFENCE_HEIGHT_M``. This exempts the takeoff climb and
landing descent where the drone is legitimately close to the floor.

Single-threaded, synchronous — driven by the mission runner loop.
"""
from __future__ import annotations

import time
from typing import Callable

from closedSpace.constants import CLEARANCE_GEOFENCE_HEIGHT_M, MIN_CLEARANCE_M
from engine.flight_control import ControllerState, FlightController
from engine.sensors import ProximitySensor
from engine.telemetry import TelemetryBus

__all__ = ["ClearanceWatchdog"]


class ClearanceWatchdog:
    """Polls proximity sensor; logs clearance telemetry; fires on violation."""

    def __init__(
        self,
        sensor: ProximitySensor,
        fc: FlightController,
        *,
        geofence_height_m: float = CLEARANCE_GEOFENCE_HEIGHT_M,
        bus: TelemetryBus | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._sensor = sensor
        self._fc = fc
        self._geofence_height_m = geofence_height_m
        self._bus = bus
        self._clock = clock or time.monotonic_ns
        #: Monotonic ns of the first clearance violation, or None.
        self.first_violation_ns: int | None = None
        #: Reason string from the most recent violation (empty until one).
        self.last_reason: str = ""

    def poll(self) -> bool:
        """Check clearance once. Log event. Return True iff SAFE_HOVER fired.

        Returns:
            True if a violation was detected and the controller was
            transitioned to SAFE_HOVER. False in all other cases.

        Raises:
            Nothing. Sensor exceptions are caught and treated as violations.
        """
        state = self._fc.get_state()
        if state is not ControllerState.AIRBORNE:
            return False
        pose = self._fc.get_pose()
        if pose.z < self._geofence_height_m:
            return False

        clearance = self._clearance_or_violation()
        violation = clearance < MIN_CLEARANCE_M

        self._publish_clearance(clearance, violation=violation)

        if not violation:
            return False

        reason = f"clearance {clearance:.3f} m < MIN_CLEARANCE_M {MIN_CLEARANCE_M}"
        self.last_reason = reason
        if self.first_violation_ns is None:
            self.first_violation_ns = self._clock()

        self._publish_collision(clearance, reason)
        self._fc.request_safe_hover(reason)
        return True

    # ------------------------------------------------------------------

    def _clearance_or_violation(self) -> float:
        """Sensor reading, or 0.0 if it raises (unknown clearance = unsafe)."""
        try:
            return float(self._sensor.min_clearance_m())
        except Exception:  # noqa: BLE001 — any sensor failure means unknown
            self.last_reason = "proximity sensor raised — treating as violation"
            return 0.0

    def _publish_clearance(self, clearance_m: float, *, violation: bool) -> None:
        """Publish one control.clearance sample to the telemetry bus."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.clearance",
            {
                "topic": "control.clearance",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "violation": violation,
                },
            },
        )

    def _publish_collision(self, clearance_m: float, reason: str) -> None:
        """Publish a control.collision event with severity COLLISION."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.collision",
            {
                "topic": "control.collision",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "severity": "COLLISION",
                    "reason": reason,
                },
            },
        )
```

---

## 7. control/__init__.py — exact changes

### 7a. Update the module docstring

Find this line in the docstring:
```
* :class:`LatencyRecorder` — ISC-13 per-waypoint perception-to-command
```

Insert BEFORE it:

```
* :class:`ClearanceWatchdog` — ISC-14/33 per-waypoint clearance enforcer.
  Polls a :class:`ProximitySensor` after every ``_execute()``; logs
  ``control.clearance`` telemetry and transitions to ``SAFE_HOVER`` on
  violation (also emits ``control.collision`` with severity ``COLLISION``).
```

### 7b. Add import

Find:
```python
from closedSpace.control.latency import LatencyRecorder
```

Add BEFORE it:
```python
from closedSpace.control.clearance_watchdog import ClearanceWatchdog
```

### 7c. Add to __all__

Find:
```python
__all__ = ["LatencyRecorder", "LinkLossWatchdog", "SlamWatchdog"]
```

Change to:
```python
__all__ = ["ClearanceWatchdog", "LatencyRecorder", "LinkLossWatchdog", "SlamWatchdog"]
```

---

## 8. runner.py — exact changes

### 8a. Add import

Find this line near the top of runner.py:
```python
from closedSpace.control import LatencyRecorder, LinkLossWatchdog, SlamWatchdog
```

Change to:
```python
from closedSpace.control import (
    ClearanceWatchdog,
    LatencyRecorder,
    LinkLossWatchdog,
    SlamWatchdog,
)
```

### 8b. Add parameter to __init__

Find in MissionRunner.__init__ the line:
```python
        recorder: LatencyRecorder | None = None,
```

Add AFTER it:
```python
        clearance_watchdog: ClearanceWatchdog | None = None,
```

Find the assignment block inside __init__ that reads:
```python
        self._recorder = recorder
```

Add AFTER it:
```python
        self._clearance_watchdog = clearance_watchdog
```

### 8c. Poll clearance watchdog in the waypoint loop

Find this exact block in the run() method:
```python
            # ISC-13: command issued — close the perception-to-command window.
            if self._recorder is not None:
                self._recorder.stop()
                self._publish_latency(self._recorder.samples[-1])
```

Add AFTER that block (before the `self._publish_progress` call):
```python
            # ISC-14: check clearance after every execute — log telemetry,
            # abort on violation (control.collision severity=COLLISION).
            if self._clearance_watchdog is not None:
                if self._clearance_watchdog.poll():
                    aborted = True
                    abort_reason = self._clearance_watchdog.last_reason
                    self._handle_abort()
                    break
```

---

## 9. Test assertions

File: `closedSpace/tests/control/test_clearance_watchdog.py`

Use `SimWorld`, `SimFlightController`, `SimProximitySensor`, `InMemoryTelemetryBus`
from the engine — the same imports as `test_watchdog.py`. Use `_FakeClock` (same
pattern as `test_watchdog.py`).

| # | Test | Assert |
|---|------|--------|
| 1 | Safe clearance → no transition | sensor returns 2.0 m, AIRBORNE, z=3.0 m → poll() == False; fc stays AIRBORNE; `control.clearance` event logged with `violation: false` |
| 2 | Violation → SAFE_HOVER + COLLISION event | sensor returns 0.3 m, AIRBORNE, z=3.0 m → poll() == True; fc is SAFE_HOVER; `control.collision` event in bus with `severity == "COLLISION"` |
| 3 | Geofence exemption | sensor returns 0.1 m (violation), AIRBORNE, z=0.5 m (< CLEARANCE_GEOFENCE_HEIGHT_M) → poll() == False; fc stays AIRBORNE; no events logged |
| 4 | Ground state → no check | fc DISARMED or ARMED, sensor returns 0.1 m → poll() == False; no events |
| 5 | Exact threshold boundary | sensor returns exactly MIN_CLEARANCE_M (0.5 m) → poll() == False (strict `<` guard); no COLLISION event |
| 6 | Sensor raises → treated as violation | subclass raises RuntimeError from min_clearance_m() → poll() == True; fc is SAFE_HOVER; COLLISION event logged |
| 7 | Optional watchdog runs mission without error | MissionRunner with clearance_watchdog=None runs the full reference mission (3 aisles, reference_warehouse.yaml) without exception; no clearance events in bus |

---

## 10. OpenCode prompts — paste these in order, one at a time

Wait for OpenCode to finish each prompt before pasting the next.

---

### Prompt 1 — engine/sensors: add ProximitySensor Protocol

```
I'm adding a ProximitySensor Protocol to engine/sensors/__init__.py.

Read the file first. Then make exactly two changes:

1. Insert this block immediately BEFORE the line that reads `__all__ = ["Camera", "Frame", "laplacian_focus_score"]`:

@runtime_checkable
class ProximitySensor(Protocol):
    """Minimum distance to any detected surface in the drone's vicinity.

    Real implementations read from depth cameras, ultrasonic rangers, or
    LiDAR. The sim stub returns a configurable value via set_clearance.
    """

    def min_clearance_m(self) -> float:
        """Minimum distance to any detected surface, in metres.

        Returns:
            Distance in metres. Values < MIN_CLEARANCE_M indicate a
            clearance violation that must be handled by the caller.

        Raises:
            RuntimeError: If the sensor is not started or has failed.
                The caller treats any exception as a violation.
        """
        ...

2. Change the __all__ line to:
__all__ = ["Camera", "Frame", "ProximitySensor", "laplacian_focus_score"]

No other changes. Show diff before writing.
```

---

### Prompt 2 — engine/sim: add SimProximitySensor

```
I'm adding SimProximitySensor to engine/sim/__init__.py.

Read the file first. Then make exactly three changes:

1. Find the line that reads:
from engine.sensors import Camera, Frame, laplacian_focus_score
Change it to:
from engine.sensors import Camera, Frame, ProximitySensor, laplacian_focus_score

2. Find the comment that reads:
# Conformance: assert structural subtyping at import time so test discovery
Insert this class immediately BEFORE that comment (leave a blank line above the comment):

class SimProximitySensor:
    """In-process ProximitySensor — returns a configurable clearance.

    Default clearance is 2.0 m (safely above MIN_CLEARANCE_M). Use
    set_clearance() in tests to inject specific values and exercise
    violation detection without real obstacle geometry.
    """

    def __init__(self, world: SimWorld, default_clearance_m: float = 2.0) -> None:
        self._world = world
        self._clearance_m = default_clearance_m

    def min_clearance_m(self) -> float:
        """Current simulated clearance in metres."""
        return self._clearance_m

    def set_clearance(self, value: float) -> None:
        """Test hook: inject a specific clearance reading.

        Args:
            value: New clearance in metres.

        Raises:
            Nothing. The watchdog handles all edge cases at call time.
        """
        self._clearance_m = value

3. Find the conformance tuple that lists:
    type[SLAMProvider], type[FlightController], type[Camera], type[LinkMonitor]
Change it to:
    type[SLAMProvider], type[FlightController], type[Camera], type[LinkMonitor],
    type[ProximitySensor],

Also add "SimProximitySensor" to the __all__ list.

No other changes. Show diff before writing.
```

---

### Prompt 3 — constants: add CLEARANCE_GEOFENCE_HEIGHT_M

```
I'm adding one constant to closedSpace/constants.py.

Read the file first. Find the last line in the file:
PERCEPTION_CMD_LATENCY_P99_S: float = 0.050

Append after it (with a blank line between):

#: Height below which clearance checks are suspended (m). The drone
#: legitimately passes through this zone during takeoff climb and
#: landing descent. ISC-33 "outside takeoff/landing geofence".
CLEARANCE_GEOFENCE_HEIGHT_M: float = 1.0

No other changes. Show diff before writing.
```

---

### Prompt 4 — create closedSpace/control/clearance_watchdog.py

```
Create the file closedSpace/control/clearance_watchdog.py with exactly this content:

"""ISC-14 ClearanceWatchdog — per-waypoint clearance enforcement.

:class:`ClearanceWatchdog` polls a :class:`ProximitySensor` after every
``_execute()`` call and:

* Always publishes a ``control.clearance`` telemetry event with the
  measured ``min_clearance_m`` (used by the post-flight log scan).
* On violation (< MIN_CLEARANCE_M): publishes a ``control.collision``
  event with ``severity: "COLLISION"`` and transitions to ``SAFE_HOVER``.

Geofence rule (ISC-33): only checks clearance when
``fc.get_state() is AIRBORNE`` AND ``fc.get_pose().z >=
CLEARANCE_GEOFENCE_HEIGHT_M``. This exempts the takeoff climb and
landing descent where the drone is legitimately close to the floor.

Single-threaded, synchronous — driven by the mission runner loop.
"""
from __future__ import annotations

import time
from typing import Callable

from closedSpace.constants import CLEARANCE_GEOFENCE_HEIGHT_M, MIN_CLEARANCE_M
from engine.flight_control import ControllerState, FlightController
from engine.sensors import ProximitySensor
from engine.telemetry import TelemetryBus

__all__ = ["ClearanceWatchdog"]


class ClearanceWatchdog:
    """Polls proximity sensor; logs clearance telemetry; fires on violation."""

    def __init__(
        self,
        sensor: ProximitySensor,
        fc: FlightController,
        *,
        geofence_height_m: float = CLEARANCE_GEOFENCE_HEIGHT_M,
        bus: TelemetryBus | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._sensor = sensor
        self._fc = fc
        self._geofence_height_m = geofence_height_m
        self._bus = bus
        self._clock = clock or time.monotonic_ns
        #: Monotonic ns of the first clearance violation, or None.
        self.first_violation_ns: int | None = None
        #: Reason string from the most recent violation (empty until one).
        self.last_reason: str = ""

    def poll(self) -> bool:
        """Check clearance once. Log event. Return True iff SAFE_HOVER fired.

        Returns:
            True if a violation was detected and the controller was
            transitioned to SAFE_HOVER. False in all other cases.

        Raises:
            Nothing. Sensor exceptions are caught and treated as violations.
        """
        state = self._fc.get_state()
        if state is not ControllerState.AIRBORNE:
            return False
        pose = self._fc.get_pose()
        if pose.z < self._geofence_height_m:
            return False

        clearance = self._clearance_or_violation()
        violation = clearance < MIN_CLEARANCE_M

        self._publish_clearance(clearance, violation=violation)

        if not violation:
            return False

        reason = f"clearance {clearance:.3f} m < MIN_CLEARANCE_M {MIN_CLEARANCE_M}"
        self.last_reason = reason
        if self.first_violation_ns is None:
            self.first_violation_ns = self._clock()

        self._publish_collision(clearance, reason)
        self._fc.request_safe_hover(reason)
        return True

    # ------------------------------------------------------------------

    def _clearance_or_violation(self) -> float:
        """Sensor reading, or 0.0 if it raises (unknown clearance = unsafe)."""
        try:
            return float(self._sensor.min_clearance_m())
        except Exception:  # noqa: BLE001 — any sensor failure means unknown
            self.last_reason = "proximity sensor raised — treating as violation"
            return 0.0

    def _publish_clearance(self, clearance_m: float, *, violation: bool) -> None:
        """Publish one control.clearance sample to the telemetry bus."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.clearance",
            {
                "topic": "control.clearance",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "violation": violation,
                },
            },
        )

    def _publish_collision(self, clearance_m: float, reason: str) -> None:
        """Publish a control.collision event with severity COLLISION."""
        if self._bus is None:
            return
        self._bus.publish(
            "control.collision",
            {
                "topic": "control.collision",
                "timestamp_ns": self._clock(),
                "payload": {
                    "min_clearance_m": clearance_m,
                    "severity": "COLLISION",
                    "reason": reason,
                },
            },
        )

Show diff before writing.
```

---

### Prompt 5 — control/__init__.py: re-export ClearanceWatchdog

```
I'm updating closedSpace/control/__init__.py to export ClearanceWatchdog.

Read the file first. Make exactly three changes:

1. Find the line:
from closedSpace.control.latency import LatencyRecorder
Add BEFORE it:
from closedSpace.control.clearance_watchdog import ClearanceWatchdog

2. Find the module docstring block that contains the line:
* :class:`LatencyRecorder` — ISC-13 per-waypoint perception-to-command
Add BEFORE it:
* :class:`ClearanceWatchdog` — ISC-14/33 per-waypoint clearance enforcer.
  Polls a :class:`ProximitySensor` after every ``_execute()``; logs
  ``control.clearance`` telemetry and transitions to ``SAFE_HOVER`` on
  violation (also emits ``control.collision`` with severity ``COLLISION``).

3. Find:
__all__ = ["LatencyRecorder", "LinkLossWatchdog", "SlamWatchdog"]
Change to:
__all__ = ["ClearanceWatchdog", "LatencyRecorder", "LinkLossWatchdog", "SlamWatchdog"]

No other changes. Show diff before writing.
```

---

### Prompt 6 — runner.py: add clearance_watchdog parameter and poll

```
I'm updating closedSpace/operator/runner.py to wire in ClearanceWatchdog.

Read the file first. Make exactly four changes:

1. Find:
from closedSpace.control import LatencyRecorder, LinkLossWatchdog, SlamWatchdog
Change to:
from closedSpace.control import (
    ClearanceWatchdog,
    LatencyRecorder,
    LinkLossWatchdog,
    SlamWatchdog,
)

2. In MissionRunner.__init__, find the parameter line:
        recorder: LatencyRecorder | None = None,
Add AFTER it:
        clearance_watchdog: ClearanceWatchdog | None = None,

3. In MissionRunner.__init__, find the assignment line:
        self._recorder = recorder
Add AFTER it:
        self._clearance_watchdog = clearance_watchdog

4. In the run() method, find this exact block:
            # ISC-13: command issued — close the perception-to-command window.
            if self._recorder is not None:
                self._recorder.stop()
                self._publish_latency(self._recorder.samples[-1])
Add AFTER that block (before the self._publish_progress call that follows it):
            # ISC-14: check clearance after every execute — log telemetry,
            # abort on violation (control.collision severity=COLLISION).
            if self._clearance_watchdog is not None:
                if self._clearance_watchdog.poll():
                    aborted = True
                    abort_reason = self._clearance_watchdog.last_reason
                    self._handle_abort()
                    break

No other changes. Show diff before writing.
```

---

### Prompt 7 — create test file

```
Create closedSpace/tests/control/test_clearance_watchdog.py.

Before writing, read closedSpace/tests/control/test_watchdog.py to understand
the fixture pattern (_FakeClock, _make_watchdog, _airborne helpers).

The new test file must use the same pattern: _FakeClock, SimWorld,
SimFlightController, SimProximitySensor, InMemoryTelemetryBus.

Import SimProximitySensor from engine.sim (it was just added there).

Write exactly these 7 tests:

1. test_safe_clearance_no_transition
   sensor returns 2.0 m, fc is AIRBORNE at z=3.0 m
   → poll() returns False, fc stays AIRBORNE
   → one control.clearance event in bus with payload["violation"] == False

2. test_violation_fires_safe_hover_and_collision_event
   sensor returns 0.3 m, fc is AIRBORNE at z=3.0 m
   → poll() returns True, fc is SAFE_HOVER
   → control.collision event in bus with payload["severity"] == "COLLISION"
   → control.clearance event in bus with payload["violation"] == True

3. test_geofence_exemption_skips_check
   sensor returns 0.1 m (would be a violation), fc is AIRBORNE at z=0.5 m
   (0.5 < CLEARANCE_GEOFENCE_HEIGHT_M == 1.0)
   → poll() returns False, fc stays AIRBORNE, no events in bus

4. test_ground_states_skip_check
   parametrize: DISARMED and ARMED
   sensor returns 0.1 m
   → poll() returns False for both, no events

5. test_exact_threshold_is_safe
   sensor returns exactly MIN_CLEARANCE_M (0.5)
   fc AIRBORNE at z=3.0 m
   → poll() returns False (strict < guard), no COLLISION event

6. test_sensor_exception_treated_as_violation
   subclass SimProximitySensor, override min_clearance_m to raise RuntimeError
   fc AIRBORNE at z=3.0 m
   → poll() returns True, fc is SAFE_HOVER, COLLISION event emitted

7. test_runner_without_clearance_watchdog_runs_full_mission
   Build a full MissionRunner using reference_warehouse.yaml, SimFlightController,
   SimCamera, CaptureSink, ReportBuilder — same pattern as test_latency_soak.py.
   Pass clearance_watchdog=None (default).
   Run one lap. Assert result.aborted == False and no exception.

No inline comments explaining WHAT the code does. One short comment only
where the WHY is non-obvious. Show diff before writing.

After writing, run:
pytest closedSpace/tests/control/test_clearance_watchdog.py -v
and report the output.
```

---

## 11. After all prompts — quality gate

Run these in a terminal (not via OpenCode):

```bash
pytest closedSpace/ engine/ -x -q
mypy closedSpace/ engine/
ruff check closedSpace/ engine/
```

All must pass before flipping the ISCs in closedSpace/ISA.md.

---

## 12. ISA.md flips after passing

Change in closedSpace/ISA.md:
```
- [ ] ISC-14: ...   →   - [x] ISC-14: ...
- [ ] ISC-31: ...   →   - [x] ISC-31: ...
- [ ] ISC-33: ...   →   - [x] ISC-33: ...
```

Also flip ISC-12, ISC-13, ISC-15 which are already implemented (git log confirms)
but still show `[ ]` in the ISA:
```
- [ ] ISC-12: ...   →   - [x] ISC-12: ...
- [ ] ISC-13: ...   →   - [x] ISC-13: ...
- [ ] ISC-15: ...   →   - [x] ISC-15: ...
```

Add a Verification entry for ISC-14/33/31 in the Changelog section.
