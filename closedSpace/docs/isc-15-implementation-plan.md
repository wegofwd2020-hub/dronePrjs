# ISC-15 Implementation Plan
## Ground-station link loss > LINK_LOSS_TIMEOUT_S → return-to-home + land

> Status: ready to implement — analysis complete, no code written yet.

---

## The requirement

> "Ground-station link loss > `LINK_LOSS_TIMEOUT_S` triggers return-to-home
> + land sequence (synthetic test harness probe)."

---

## 1. Files that need to change

| File | Change |
|------|--------|
| **New** `engine/link/__init__.py` | `LinkMonitor` Protocol: `heartbeat() -> None`, `last_heartbeat_ns() -> int` |
| `engine/sim/__init__.py` | Add `SimLinkMonitor` implementing `LinkMonitor`; add `silence()` test hook; add to structural conformance tuple |
| `closedSpace/constants.py` | Add `LINK_LOSS_TIMEOUT_S = 5.0`, `LINK_POLL_INTERVAL_S = 0.5` |
| **New** `closedSpace/control/link_watchdog.py` | `LinkLossWatchdog` class — polls heartbeat age, triggers RTH + land |
| `closedSpace/operator/runner.py` | Accept optional `link_watchdog`; poll after SLAM watchdog each loop iteration |
| `closedSpace/run.py` | Wire `LinkLossWatchdog(link=link_monitor, fc=fc, home=home_pose)` into runner |

**Engine rule note:** adding `engine/link/__init__.py` is *additive* — no existing
Protocol surface changes. `SimLinkMonitor` in `engine/sim/__init__.py` is also
additive. openSpace has no Python code yet; no cross-domain update needed.
The structural conformance tuple at the bottom of `engine/sim/__init__.py`
must be extended to include `SimLinkMonitor`.

---

## 2. RTH behaviour and state machine

```
AIRBORNE ──link silent > LINK_LOSS_TIMEOUT_S──► goto(home) ──► LANDING ──► DISARMED
SAFE_HOVER ──link silent > LINK_LOSS_TIMEOUT_S──► LANDING ──► DISARMED
                                                   (no goto — refused in SAFE_HOVER)
DISARMED / ARMED / LANDING ──link silent──► (watchdog skips — no action)
```

**RTH sequence from AIRBORNE:**
1. `fc.goto(home.x, home.y, home.z, home.yaw_deg)` — return to takeoff pad
2. `fc.land()` — descend and disarm

**RTH sequence from SAFE_HOVER:**
- `fc.goto()` raises `RuntimeError` in SAFE_HOVER (ISC-12 design rule).
- Skip goto; call `fc.land()` directly.
- The drone is already parked safely — immediate landing is the correct recovery.

**Priority in runner loop (highest → lowest):**
1. SLAM watchdog (`SlamWatchdog.poll()`) — ISC-12
2. Link watchdog (`LinkLossWatchdog.poll()`) — ISC-15
3. Operator abort signal

SLAM loss preempts link-loss because SAFE_HOVER is a stable hover state;
the link watchdog then sees SAFE_HOVER and executes a direct land if link
is also lost.

---

## 3. LinkMonitor Protocol — `engine/link/__init__.py`

```python
# engine/link/__init__.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class LinkMonitor(Protocol):
    """Tracks ground-station keepalive timestamps.

    The ground station calls heartbeat() on every keepalive received.
    The watchdog compares last_heartbeat_ns() against the monotonic clock
    to determine elapsed silence.
    """

    def heartbeat(self) -> None:
        """Record receipt of a ground-station keepalive. Thread-safe."""
        ...

    def last_heartbeat_ns(self) -> int:
        """Monotonic ns of the most recent heartbeat. Returns 0 if never
        received (treated as maximum elapsed time by the watchdog)."""
        ...
```

`SimLinkMonitor` in `engine/sim/__init__.py`:
```python
class SimLinkMonitor:
    def __init__(self, clock: Callable[[], int]) -> None:
        self._clock = clock
        self._last_ns: int = clock()   # starts alive
        self._silenced: bool = False

    def heartbeat(self) -> None:
        """Record a keepalive (no-op if silenced)."""
        if not self._silenced:
            self._last_ns = self._clock()

    def last_heartbeat_ns(self) -> int:
        return self._last_ns

    def silence(self) -> None:
        """Test hook: stop recording heartbeats — simulates link drop."""
        self._silenced = True
```

---

## 4. LinkLossWatchdog design — `closedSpace/control/link_watchdog.py`

```python
# closedSpace/control/link_watchdog.py

class LinkLossWatchdog:
    def __init__(
        self,
        link: LinkMonitor,
        fc: FlightController,
        home: Pose,
        *,
        timeout_s: float = LINK_LOSS_TIMEOUT_S,
        poll_interval_s: float = LINK_POLL_INTERVAL_S,
        clock: Callable[[], int] | None = None,   # monotonic ns
    ) -> None: ...

    def poll(self) -> bool:
        """Check link age once. Return True iff RTH+land was triggered.

        - Only acts from AIRBORNE or SAFE_HOVER.
        - Guard is strict `>` against timeout_ns — exactly-at-timeout
          does not trigger.
        - From AIRBORNE: goto(home) then land().
        - From SAFE_HOVER: land() directly (goto raises RuntimeError there).
        - Records first_loss_ns on the monotonic clock at detection time.
        - If last_heartbeat_ns() raises, treats as full elapsed (unknown = unsafe).
        - Idempotent once landed: LANDING/DISARMED ground-state gate returns False.
        """
        ...
```

---

## 5. Home pose derivation — `closedSpace/run.py`

The takeoff pad is the known home position. Extract it from the plan before
constructing the watchdog:

```python
# After slam.start() / cam.start()

from engine.types import Pose

# First waypoint is always "takeoff"; its (x,y) is the pad center.
takeoff_wp = p.waypoints[0]
home_pose = Pose(
    x=takeoff_wp.x,
    y=takeoff_wp.y,
    z=takeoff_wp.z,          # hover height — descend via land()
    yaw_deg=0.0,
    timestamp_ns=world.now_ns(),
)
link_monitor = SimLinkMonitor(clock=world.now_ns)

runner = MissionRunner(
    ...,
    watchdog=SlamWatchdog(slam=slam, fc=fc, clock=world.now_ns),
    link_watchdog=LinkLossWatchdog(
        link=link_monitor, fc=fc, home=home_pose, clock=world.now_ns
    ),
)
```

---

## 6. Test assertions

File: `closedSpace/tests/control/test_link_watchdog.py`

| # | Test | Assert |
|---|------|--------|
| 1 | RTH fires — AIRBORNE + silence > timeout | goto(home) called then land → state is `DISARMED` |
| 2 | Active link — no RTH | link alive → `poll()` returns False, state stays `AIRBORNE` |
| 3 | No ground transition — DISARMED/ARMED + silence | no RTH; state unchanged |
| 4 | Strict boundary — elapsed == timeout_ns | no trigger (guard is `>` not `>=`) |
| 5 | SAFE_HOVER + silence > timeout | `land()` called directly; no `goto()`; state → `DISARMED` |
| 6 | Event logged — `flight_control.state` bus event with `timestamp_ns` field | published on RTH trigger |
| 7 | `first_loss_ns` recorded | non-None after first trigger; matches monotonic clock at poll time |
| 8 | Idempotent — poll after landing (DISARMED) | returns False; no second RTH attempt |

---

## 7. Edge cases

| Case | Handling |
|------|----------|
| Link recovers between polls | Irrelevant — only elapsed time at poll time matters |
| `last_heartbeat_ns()` raises | Catch; treat elapsed as max int → trigger RTH+land (unknown = unsafe) |
| SLAM loss fires first (SAFE_HOVER) | Link watchdog sees SAFE_HOVER → `land()` directly; no `goto()` |
| LANDING state when polled | Watchdog skips — landing already in progress, nothing to do |
| Link loss during RTH `goto()` | Sim is instant; on real hardware `goto` races the next poll but `land()` follows immediately after |
| `LINK_POLL_INTERVAL_S` too large | Constructor raises `ValueError` if `poll_interval_s > timeout_s / 2` so at least two polls fit in the timeout window |
| First heartbeat never received (`last_heartbeat_ns() == 0`) | Elapsed = `now - 0` >> any reasonable timeout → RTH fires on first poll while AIRBORNE |
| Runner loop has no link watchdog wired | Optional; `link_watchdog=None` skips the poll (same pattern as `SlamWatchdog`) |

---

## 8. OpenCode prompt to start implementation

Paste this into OpenCode **Build** mode:

```
I'm implementing ISC-15 in the closedSpace sub-project of dronePrjs.
The full plan is in closedSpace/docs/isc-15-implementation-plan.md — read it first.
Also read closedSpace/docs/isc-12-implementation-plan.md and the finished
ISC-12 code (closedSpace/control/watchdog.py, closedSpace/tests/control/test_watchdog.py)
so you match the existing patterns exactly.

Implement in this order:
1. Create engine/link/__init__.py with the LinkMonitor Protocol
2. Add SimLinkMonitor to engine/sim/__init__.py; extend the structural
   conformance tuple at the bottom of that file to include SimLinkMonitor
3. Add LINK_LOSS_TIMEOUT_S and LINK_POLL_INTERVAL_S to closedSpace/constants.py
4. Create closedSpace/control/link_watchdog.py with LinkLossWatchdog
5. Update closedSpace/operator/runner.py to accept optional link_watchdog
   and poll it after SlamWatchdog in the loop
6. Update closedSpace/run.py to derive home_pose from the plan and wire
   LinkLossWatchdog with SimLinkMonitor(clock=world.now_ns)
7. Write closedSpace/tests/control/test_link_watchdog.py covering all 8 assertions

Follow the engine rules: engine/link/__init__.py is additive (no existing
interface changes); the structural conformance tuple in engine/sim/__init__.py
must include SimLinkMonitor.
Run pytest after each file to catch regressions early.
```
