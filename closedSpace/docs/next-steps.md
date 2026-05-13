# closedSpace — Next Steps (v1 roadmap)

> Forward-looking companion to `ISA.md` (the contract) and
> `use-cases.md` (the narrative). This document is the **work order**:
> what to build next, in what sequence, what unblocks what, and the
> open decisions that gate certain phases.
>
> Effort estimates are deliberate-day units (one engineer, focused).
> Status is `not-started`, `in-progress`, or `done`.

---

## At-a-glance roadmap

| Phase | Theme | Effort (days) | Blocks downstream | Status |
|---|---|---|---|---|
| 0 | Foundations: env, repo, engine skeleton | 1–2 | All Python work | done |
| 1 | MissionPlanner | 3–5 | UC-1 spine, simulator wiring | done |
| 2 | Engine contracts (Protocols + stubs) | 2–3 | Simulator + flight stack | done |
| 3 | Simulator bring-up | 5–10 | All flight verification | in-progress (D1/D2 answered 2026-05-13) |
| 4 | Capture + Storage + Report | 4–6 | UC-1 reaches end-to-end | done |
| 5 | OperatorConsole + preflight | 3–4 | UC-1 user-facing | done |
| 6 | Quality gates + anti-scope guards | 2–3 | Production readiness | done |
| 7 | MapBuilderFromWMS | 5–10 | Pilot deployment | sketched |
| 8 | Pilot mission (real warehouse) | 5+ | v1 done | not-started |

Total v1 effort, single engineer, before pilot: **~25–45 deliberate-days**,
strongly dependent on simulator choice (Phase 3) and whether real
hardware bring-up runs in parallel.

---

## Open decisions — answer before Phase 3

These three decisions shape the rest of the work. Each has a
recommendation, not a mandate; the answers belong in `## Decisions` of
the ISA once made.

### D1: Simulator vs hardware-first

**Question:** Does v1 verify on simulator, real hardware, or both?

| Option | Pros | Cons | Time-to-first-flight |
|---|---|---|---|
| **Sim-first** (Gazebo/PX4 SITL or AirSim) | Fast iteration, no flight permits, no crash cost, automated CI possible | Sensor fidelity gaps; simulator≠reality especially for SLAM in featureless aisles | ~1 week |
| **Hardware-first** (real drone, simple test space) | Real physics, real sensors, proves the thing works | Requires drone, space, permits, crash tolerance, slow iteration | ~3–4 weeks |
| **Both, sim leads** | Sim catches 80% of bugs, hardware catches the long tail | Two stacks to maintain | ~2 weeks |

**Recommendation:** sim leads, hardware follows. Wire the engine to
both behind one Protocol so unit + integration tests run in sim;
hardware sessions become a manual gate.

### D2: Which simulator

**Question:** If we go sim-first, which one?

| Option | Notes |
|---|---|
| **Gazebo + PX4 SITL** | Industry standard for open-source drone work; full PX4 software-in-the-loop; rich sensor models incl. RGB-D, LiDAR; large community. Heavy install. |
| **AirSim / Cosys-AirSim** | Unreal Engine renderer; visually realistic for indoor warehouse; good camera sim. AirSim itself is unmaintained — Cosys-AirSim is the current fork. Heavy install. |
| **Isaac Sim (NVIDIA)** | Photorealistic, good for VIO testing, GPU-heavy, license. |
| **Minimal in-process Python sim** | We write it. Pure kinematic, no rendering, returns idealized SLAM poses + synthetic image stubs for capture. Great for unit tests, useless for real perception validation. |
| **Two-tier (in-process + Gazebo)** | Unit tests against the in-process kinematic sim (fast, deterministic). Integration tests against Gazebo (slow, realistic). |

**Recommendation:** two-tier. NS-3.1 builds the in-process kinematic
sim (1–2 days, pays for itself in test speed). NS-3.2 wires Gazebo
later for integration tests.

### D3: Flight stack

**Question:** PX4? ArduPilot? Proprietary?

| Option | Notes |
|---|---|
| **PX4** | Modern, MAVLink, well-supported, large community; default for Skydio-class autonomous work |
| **ArduPilot** | More mature, more conservative, similar capability via MAVLink |
| **Proprietary / SDK-based** | DJI SDK, Skydio SDK, Verity SDK — fastest path to working hardware, vendor lock-in |
| **Defer** | Engine contracts are flight-stack-agnostic; pick at hardware bring-up |

**Recommendation:** defer. Engine `flight_control` Protocol abstracts
this. Pick when D1 hardware path activates.

---

## Phase 0 — Foundations

**Goal:** Make the repo a real Python project with a runnable test
suite and a real engine package, so subsequent phases compile.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-0.1 | Create venv at `dronePrjs/.venv`; `pip install -e .[dev]` so the existing pytest suite runs | 0.25d | One-time. Confirms `closedSpace/tests/map/test_*.py` pass under real pytest, not just smoke runner. |
| NS-0.2 | Initialize git repo at `dronePrjs/`; commit current state; create `main` branch | 0.25d | Should already be clean — current artifacts are committable as-is. |
| NS-0.3 | Add `.gitignore` for `__pycache__`, `.venv/`, `*.pyc`, `.pytest_cache` | 0.1d | Smoke-runner left pycache dirs. |
| NS-0.4 | Scaffold `engine/` package: `engine/__init__.py`, `engine/localization/__init__.py`, `engine/flight_control/__init__.py`, `engine/telemetry/__init__.py`, `engine/sensors/__init__.py` — empty modules | 0.25d | Required so `closedSpace.map`'s docstrings referencing `engine.localization.SLAMProvider` aren't aspirational. |
| NS-0.5 | Implement ISC-5 (map dump round-trip) — add `closedSpace.map.dump(map, path)` mirroring `load`, plus a test | 0.5d | Last loose end on the loader feature. |
| NS-0.6 | Add a `Makefile` (or `Justfile`) with `make test`, `make lint`, `make typecheck`, `make all` | 0.25d | One command per quality gate. |

**Exit criteria:** `make all` passes against the current code; ISC-5
flips to `[x]`; `engine/` is importable.

---

## Phase 1 — MissionPlanner

**Goal:** Implement the path-derivation contract from
`docs/map-schema.md` §10 — pure function from Map → ordered Waypoint
list.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-1.1 | `closedSpace/mission/types.py` — `Waypoint`, `MissionPlan`, `MissionConfig` (with all the §10.3 tunables) | 0.5d | Frozen dataclasses, mirroring `map/types.py` style. |
| NS-1.2 | `closedSpace/mission/plan.py` — `plan(map, config) → MissionPlan`. Pure, deterministic, no IO | 1–2d | Implements §10 exactly: takeoff → per-aisle traversal → inter-aisle transit → landing. |
| NS-1.3 | `closedSpace/mission/transit.py` — inter-aisle free-space router, no-go-zone aware | 0.5–1d | v1 can be naive: rectilinear path at AISLE_TRAVERSAL_HEIGHT_M, panic if no-go zone blocks it. Smarter routing is post-v1. |
| NS-1.4 | Tests in `closedSpace/tests/mission/`: capture-count matches map, total path length within ±5% of hand-computed, boustrophedon ordering, no-go avoidance, determinism (same input → same bytes) | 1d | Satisfies ISC-6 through ISC-10. |
| NS-1.5 | Hand-derive expected path length for `reference_warehouse.yaml` and store as a fixture (`tests/fixtures/missions/reference_plan.json`) | 0.25d | Locks in the ±5% target. |

**Exit criteria:** ISC-6 through ISC-10 all `[x]`; `plan(reference_map, default_config)` returns 64 capture waypoints + transit waypoints; total path length is documented and verified.

---

## Phase 2 — Engine contracts

**Goal:** Define the Protocol surface every flight-platform-specific
implementation must conform to. No actual platform code yet — just
interfaces and an in-process stub.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-2.1 | `engine/localization/__init__.py` — `SLAMProvider` Protocol: `get_pose() -> Pose`, `confidence() -> float`, lifecycle hooks | 0.5d | Pose type lives in engine, not closedSpace (cross-domain). |
| NS-2.2 | `engine/flight_control/__init__.py` — `FlightController` Protocol: arm, disarm, takeoff, land, goto(waypoint), hold | 0.5d | Subscribe-style state callbacks. |
| NS-2.3 | `engine/telemetry/__init__.py` — `TelemetryBus` Protocol: pub/sub, JSONL log writer | 0.25d | |
| NS-2.4 | `engine/sensors/__init__.py` — `Camera` Protocol: capture(), Laplacian focus score helper | 0.25d | |
| NS-2.5 | `engine/sim/__init__.py` — in-process kinematic stubs implementing all four Protocols | 1d | Returns idealized poses, synthetic image bytes, fake telemetry. Drives unit tests in NS-1.4 and Phase 4. |
| NS-2.6 | Add anti-scope guard test: `engine/` does not import any `closedSpace` symbol | 0.25d | Satisfies ISC-36. |

**Exit criteria:** `closedSpace` can run a planned mission against the
in-process sim end-to-end with no real-hardware dependency.

---

## Phase 3 — Simulator bring-up (decision-gated)

**Goal:** Wire engine Protocols to a realistic simulator for
integration tests.

This phase only proceeds after **D1** (sim-first vs hardware-first) and
**D2** (which simulator) are answered.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-3.1 | Two-tier sim: in-process is already done in NS-2.5; this task is to add the Gazebo/AirSim integration tier | 3–5d | Heavy install lift. Worth running in a Docker container. |
| NS-3.2 | Build a Gazebo/AirSim world matching `reference_warehouse.yaml` | 1–2d | Aisles + racks as static meshes. |
| NS-3.3 | SLAMProvider impl backed by simulator pose + noise model | 1d | Inject configurable drift to test ISC-12 (SLAM loss recovery). |
| NS-3.4 | Camera impl backed by simulator's RGB sensor | 0.5d | Capture image bytes, write to disk same as real camera. |
| NS-3.5 | End-to-end mission test in simulator: load map → plan → fly → capture → report | 1d | First time UC-1 runs end-to-end. |

**Exit criteria:** UC-1 completes in simulator; mission report shows
≥ 95% coverage on the reference fixture; ISC-13 (latency) and ISC-14
(clearance) probes pass against simulator telemetry.

---

## Phase 4 — Capture, Storage, Report

**Goal:** Parts of UC-1 that aren't flight-control. Can run in parallel
with Phase 3 if a developer is bored of waiting.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-4.1 | `closedSpace/capture/` — Camera consumer, focus-score gate, sidecar JSON writer, filename pattern | 1d | Satisfies ISC-16 through ISC-20. |
| NS-4.2 | `closedSpace/storage/` — local-first writer, post-flight backend sync, sync-pending markers | 1–2d | Satisfies ISC-21, ISC-22, ISC-32. Backend choice (S3? local NAS?) is open — start with local FS, add an `RemoteSink` Protocol. |
| NS-4.3 | `schemas/mission_report.schema.json` + `closedSpace/report/` builder | 1d | Satisfies ISC-23, ISC-24, ISC-25. |
| NS-4.4 | Tests across all three modules; integrates with Phase 1's plan + Phase 2's sim | 1d | |

**Exit criteria:** UC-5 and UC-8 ISCs all `[x]`; `mission_report.json`
validates against its schema after a sim run.

---

## Phase 5 — OperatorConsole + preflight

**Goal:** UC-1 step 1–4 (CLI), UC-3 (preflight gate), UC-6 abort
handling.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-5.1 | `closedSpace/run.py` — `python -m closedSpace.run --map <path>` entry point. Argument parsing, plan summary, confirmation prompt | 0.75d | Satisfies ISC-26. |
| NS-5.2 | Pre-flight checklist runner: battery, calibration, map signature, free-space, takeoff-pad-in-coverage, staleness | 1d | Satisfies ISC-28, ISC-34, ISC-44. |
| NS-5.3 | Abort-key handling — async stdin read; transition drone to LAND_NOW within 500 ms | 0.5d | Satisfies ISC-27. |
| NS-5.4 | 1 Hz progress log + structured event stream | 0.5d | Satisfies ISC-29. |
| NS-5.5 | Operator README — "from cold start to landed in 15 minutes" walkthrough | 0.5d | Antecedent for ISC-42. |

**Exit criteria:** UC-1 + UC-3 reachable end-to-end via the CLI in
simulator; ISC-42 antecedent walkthrough is testable with a non-pilot.

---

## Phase 6 — Quality gates + anti-scope guards

**Goal:** Make the constraint-derived ISCs auditable in CI, not just in
prose.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-6.1 | `pytest --cov=closedSpace --cov-fail-under=80` wired into `make test` and CI | 0.25d | Satisfies ISC-37. |
| NS-6.2 | `mypy --strict closedSpace/` clean | 0.5d | Satisfies ISC-38. May require some `# type: ignore` triage. |
| NS-6.3 | `ruff check closedSpace/` clean | 0.25d | Satisfies ISC-39. |
| NS-6.4 | Docstring linter (e.g. `pydocstyle` with OpenSpec config) | 0.5d | Satisfies ISC-40. |
| NS-6.5 | Test-pair linter — every `closedSpace/**/*.py` has a `closedSpace/tests/**/test_*.py` mirror | 0.5d | Satisfies ISC-41. Small custom script. |
| NS-6.6 | Anti-scope CI step: `rg "GPSProvider" closedSpace/ engine/` returns zero, `rg -E "import (cv2|easyocr|paddleocr|ultralytics)" closedSpace/` returns zero | 0.25d | Satisfies ISC-30, ISC-35. |
| NS-6.7 | GitHub Actions workflow (or chosen CI) running all of the above on PR | 0.5d | |

**Exit criteria:** All cross-cutting and anti-scope ISCs (ISC-30,
ISC-35, ISC-36, ISC-37–41) `[x]`; CI is green on `main`.

---

## Phase 7 — MapBuilderFromWMS

**Goal:** UC-4. Without this, every new warehouse is hand-authored
YAML, which doesn't scale past pilot.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-7.1 | `WmsExport` Protocol + first adapter (suggested: SAP EWM CSV — broadest deployment) | 1–2d | |
| NS-7.2 | Floor plan parser via `ezdxf` (DXF/DWG) | 1–2d | Coverage polygon + column extraction. |
| NS-7.3 | Rack vendor spec parser (YAML format we define) | 0.5d | |
| NS-7.4 | Survey overlay schema + parser | 0.5d | |
| NS-7.5 | `builder.py` — composer + diff against existing map + validate before write | 1d | |
| NS-7.6 | CLI: `closedSpace map from-wms ...` | 0.5d | |
| NS-7.7 | Tests with synthetic inputs for each adapter | 1d | |

**Exit criteria:** Given the four input artifacts for the reference
warehouse, the builder produces a YAML byte-for-byte equivalent (modulo
formatting) to the hand-authored fixture.

**Defer to Phase 7.b:** Manhattan Active WM and Fishbowl adapters.

---

## Phase 8 — Pilot mission (real warehouse)

**Goal:** Validate the system end-to-end in one real warehouse with one
real drone.

This phase is mostly logistics, not code. Listed here so it isn't
forgotten.

| ID | Task | Effort | Notes |
|---|---|---|---|
| NS-8.1 | Identify pilot warehouse + operator partner | — | Sales / business-dev. |
| NS-8.2 | Real-hardware bring-up: pick drone, integrate flight stack with engine, validate SLAM holds in real aisles | 5–10d | Where D3 (flight stack) gets answered. |
| NS-8.3 | Surveyor-led map authoring (UC-9 / UC-4) for the pilot warehouse | 0.5–1d | Half-day site survey. |
| NS-8.4 | Run UC-3 → UC-1 → UC-8 end-to-end in the real warehouse | 1–2d | First real-world run. |
| NS-8.5 | RedTeam pass against the post-pilot ISA — what surprised us, what didn't | 0.5d | Skill: `RedTeam`. |
| NS-8.6 | Update ISA Changelog with conjecture/refutation/learning entries from the pilot | 0.5d | |

**Exit criteria:** Pilot warehouse runs a successful inventory mission;
mission report shows ≥ 95% coverage; no collision events; no clearance
violations; operator successfully ran cold start to landed within 15
minutes.

---

## Suggested sequencing

For a single engineer working solo, the recommended path is:

1. **Phase 0** (1–2d) — sets up the runway.
2. **Phase 1 + Phase 2 in parallel** (3–5d total, if interleaved) —
   MissionPlanner depends only on the map types, Engine contracts
   depend only on what we already wrote about poses/control. Both
   can be drafted before either is finished.
3. **Decisions D1 / D2 / D3 made.** Don't start Phase 3 until they
   are recorded in `## Decisions` of the ISA.
4. **Phase 3** (5–10d) — simulator bring-up, sim-first.
5. **Phase 4 + Phase 5 in parallel** (5–7d if work can split) —
   capture/storage/report on one branch, operator console on another.
6. **Phase 6** (2–3d) — close out the auditability ISCs.
7. **Phase 7** (5–10d) — first WMS adapter only; defer the rest.
8. **Phase 8** (10d+) — pilot.

Total: about **30–50 deliberate-days** before the first real mission.

---

## Risk register

The risks worth tracking. Each one earns a Decision in the ISA when
mitigated or accepted.

| ID | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| R1 | SLAM diverges in featureless aisles (rack faces look identical every meter) | high | high | Inject AprilTag fiducials at aisle endpoints; validate in sim with low-feature texture |
| R2 | 0.5 m clearance is too tight when racks have protruding stock the map doesn't know about | medium | high | Onboard depth sensor + reactive-stop; wider clearance budget if sensor confirms |
| R3 | Battery sag at altitude shortens the 15-min budget | medium | medium | Conservative MAX_MISSION_DURATION_S; budget 70% of nameplate; abort early if telemetry shows divergence |
| R4 | Map staleness goes undetected for weeks | medium | medium | UC-3 staleness gate + scheduled re-survey reminder; eventually drone-detected drift (post-v1) |
| R5 | Simulator chosen turns out to be unmaintained or wrong fit | low | medium | Two-tier sim approach — in-process sim is owned; second tier is replaceable |
| R6 | Real-hardware bring-up reveals an interface gap in the engine Protocol | medium | medium | Engine Protocols stay narrow; broaden only with concrete hardware feedback |
| R7 | First WMS adapter (SAP EWM) doesn't generalize — every WMS export shape is too different | medium | low | Adapter Protocol is the abstraction; differences become per-adapter code, not core code |

---

## Open questions for {{PRINCIPAL_NAME}} to answer

These are the questions the work is currently waiting on:

1. **Sim-first or hardware-first?** (D1)
2. **Which simulator?** (D2) — recommendation: in-process kinematic
   sim now, Gazebo/PX4-SITL for integration tests.
3. **Which flight stack?** (D3) — can defer.
4. **Backend for image sync** — S3? Local NAS? Customer-supplied?
5. **Real camera and resolution target** — affects ISC-19 threshold.
6. **First pilot warehouse partner** — is this a real customer engagement
   or an internal POC?
7. **CI host** — GitHub Actions, GitLab CI, self-hosted?
8. **License** — proprietary, MIT, GPL? Affects how aggressively we can
   pull in deps like `ezdxf`, `ifcopenshell`, simulator code.

Each answer should be recorded in the ISA's `## Decisions` so future
work can find the rationale.

---

## Where to look next

- `ISA.md` — verifiable contract, 44 ISCs, 10 Features, Decisions log
- `docs/use-cases.md` — narrative view of UC-1 through UC-9
- `docs/map-schema.md` — warehouse-map data model + path-derivation
  contract for Phase 1
- `closedSpace/map/` — the only feature implemented today
- `closedSpace/tests/map/` — the only test suite, runs via smoke
  runner today, runs via real pytest after Phase 0

---

## How this document evolves

After each phase completes:

1. Mark phase status `done` in the at-a-glance table.
2. Update affected Features in `ISA.md` with shipped artifact paths.
3. Flip newly-verified ISCs from `[ ]` to `[x]` with Verification
   evidence.
4. Add a Changelog entry in `ISA.md` for any conjecture/refutation/learning
   surfaced during the phase.
5. If new work surfaced that wasn't in this document, add a new NS-N.M
   task; if a phase was over-scoped, mark sub-tasks as deferred and
   capture in Decisions.
