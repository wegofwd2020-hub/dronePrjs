# ISC-12 Implementation Plan
## Mid-mission SLAM loss → SAFE_HOVER within 200 ms

> Status: ready to implement — analysis complete, no code written yet.

---

## The requirement

> "Mid-mission loss of SLAM tracking transitions the drone to SAFE_HOVER state
> within 200 ms (logged with state-transition timestamp)."

---

## 1. Files that need to change

| File | Change |
|------|--------|
| `engine/flight_control/__init__.py` | Add `request_safe_hover(reason: str) -> None` to `FlightController` Protocol |
| `engine/sim/__init__.py` | Implement `request_safe_hover` on `SimFlightController` (delegates to `force_safe_hover`); relax `land()` to also accept `SAFE_HOVER` state |
| `closedSpace/constants.py` | Add `SLAM_CONFIDENCE_THRESHOLD = 0.5`, `SLAM_POLL_INTERVAL_S = 0.02`, `SAFE_HOVER_MAX_LATENCY_S = 0.2` |
| **New** `closedSpace/control/watchdog.py` | `SlamWatchdog` class — polls confidence, triggers transition |
| `closedSpace/operator/runner.py` | Accept optional watchdog; poll each loop iteration; handle `SAFE_HOVER` in `_handle_abort` |
| `closedSpace/run.py` | Wire `SlamWatchdog(slam=slam, fc=fc)` into runner |

**Note:** Engine changes are required — `request_safe_hover` does not exist on the
Protocol yet. `force_safe_hover` exists only on `SimFlightController` directly,
not on the Protocol surface. Per engine rules: any change to engine interfaces
must update **both** closedSpace and openSpace in the same change.

---

## 2. SAFE_HOVER state machine

```
DISARMED ──arm()──► ARMED ──takeoff()──► AIRBORNE
                                            │       ▲ (self-loop, idempotent)
                               confidence < threshold
                               within 200 ms         │
                                            ▼
                                        SAFE_HOVER ──land()──► LANDING ──► DISARMED
```

**Rules while in SAFE_HOVER:**
- `goto()` → `RuntimeError` (refuses)
- `takeoff()` → `RuntimeError` (refuses)
- `land()` → allowed (operator-initiated recovery)
- second `request_safe_hover()` → idempotent self-loop, no new event

The watchdog owns the `AIRBORNE → SAFE_HOVER` trigger. The runner stops
commanding waypoints on `SAFE_HOVER` and publishes `mission.finished`
with `aborted=True`.

---

## 3. SlamWatchdog design

```python
# closedSpace/control/watchdog.py

class SlamWatchdog:
    def __init__(
        self,
        slam: SLAMProvider,
        fc: FlightController,
        *,
        threshold: float = SLAM_CONFIDENCE_THRESHOLD,
        poll_interval_s: float = SLAM_POLL_INTERVAL_S,
        clock: Callable[[], int] | None = None,   # monotonic ns
    ) -> None: ...

    def poll(self) -> bool:
        """Check confidence once. Returns True if transition fired.

        - Only transitions if fc.get_state() is AIRBORNE.
        - Records first_loss_ns on the shared monotonic clock.
        - Calls fc.request_safe_hover(reason=f"slam confidence {c:.3f} < {threshold}").
        - Wraps confidence() exceptions as domain error but still transitions.
        - Idempotent: returns False if already SAFE_HOVER.
        """
        ...
```

---

## 4. Test assertions

File: `closedSpace/tests/control/test_watchdog.py`

| # | Test | Assert |
|---|------|--------|
| 1 | Transition fires | confidence < threshold while AIRBORNE → state is `SAFE_HOVER` |
| 2 | Latency ≤ 200 ms | fake ns clock; delta between loss and `StateChange.timestamp_ns` ≤ 200,000,000 ns |
| 3 | Event logged | `flight_control.state` bus event published with `timestamp_ns` field |
| 4 | No ground transition | DISARMED/ARMED + low confidence → no transition |
| 5 | Strict boundary | confidence exactly == threshold → no transition (guard is `<` not `<=`) |
| 6 | Idempotency | second poll while already `SAFE_HOVER` → no second event fired |
| 7 | confidence() raises | exception caught → still transitions (unknown = unsafe) |

---

## 5. Edge cases

| Case | Handling |
|------|----------|
| Confidence recovers between polls | Irrelevant — if below threshold at poll time, transition fires |
| `confidence()` raises exception | Catch, treat as loss → transition anyway (unknown tracking = unsafe) |
| Confidence exactly == threshold | No transition — guard is strict `<` |
| Already `SAFE_HOVER` when polled | `request_safe_hover` is idempotent — no new `StateChange` event |
| SLAM loss during `LANDING` | Watchdog skips — only transitions from `AIRBORNE` |
| Runner mid-`goto()` when SAFE_HOVER fires | Sim is instant; runner checks state each loop iteration — catches at next waypoint |
| Two watchdog poll threads | Don't — watchdog is single-threaded, called synchronously by runner loop |

---

## 6. OpenCode prompt to start implementation

Paste this into OpenCode **Build** mode:

```
I'm implementing ISC-12 in the closedSpace sub-project of dronePrjs.
The full plan is in closedSpace/docs/isc-12-implementation-plan.md — read it first.

Implement in this order:
1. Add request_safe_hover() to engine/flight_control/__init__.py Protocol
2. Implement it on SimFlightController in engine/sim/__init__.py;
   also relax land() to accept SAFE_HOVER state
3. Add the three constants to closedSpace/constants.py
4. Create closedSpace/control/__init__.py and closedSpace/control/watchdog.py
5. Update closedSpace/operator/runner.py to accept + poll the watchdog
6. Update closedSpace/run.py to wire SlamWatchdog in
7. Write closedSpace/tests/control/test_watchdog.py covering all 7 assertions

Follow the engine rules: engine interface changes must not break openSpace.
Run pytest after each file to catch regressions early.
```
