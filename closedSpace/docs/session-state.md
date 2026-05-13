# Session State — closedSpace

> Pickup point. Read this first when resuming work; it points at the
> four canonical sources for everything we know about the project.

**Last updated:** 2026-05-13
**Current phase:** observe (project ISA `phase: observe`, `progress: 29/44`)
**Roadmap:** Phases 0, 1, 2, 4, 5 complete. Operator can run an entire
mission via `python -m closedSpace.run --map <path>` — plan summary,
preflight gate, explicit confirmation, per-waypoint progress log,
mission report on disk. D1–D3 still gate Phase 3 simulator bring-up.
Next unblocked chunk: Phase 6 (quality gates polish — coverage,
docstring lint, file-pair lint).

---

## Start here, in this order

1. **`ISA.md`** — verifiable contract. 44 ISCs, 10 Features, full
   `## Decisions` log of every iteration (1 → 7). Frontmatter has
   `progress` and `phase`. **Read the most recent Decisions block
   first** — it's the freshest signal of what we just did.
2. **`docs/next-steps.md`** — 9-phase roadmap. Three open decisions
   (D1, D2, D3) gate Phase 3; phase 0 is unblocked and is the right
   first move on resume.
3. **`docs/use-cases.md`** — 9 use cases (UC-1 through UC-9), human-
   readable narrative tied back to ISA Features and ISCs.
4. **`docs/map-schema.md`** + **`docs/drones.md`** — the deep-dive
   companions for map data model and drone-platform survey.

---

## What's done

- Project ISA / PRD with 44 atomic ISCs, 10 Features.
- Warehouse map data model: schema doc, JSON Schema, reference fixture
  (64 capture positions).
- Map loader + validator implemented in Python: `closedSpace/map/`.
- Optional provenance fields (`surveyed_at`, `surveyed_by`) added in
  schema v1, threaded through loader, ISC-43 verified.
- pyproject.toml at project root with pytest config + deps declared.
- Use cases + roadmap + drone survey all written under `docs/`.
- **Phase 0 complete (2026-05-13):** git repo on GitHub, `.gitignore`,
  `.venv` + editable install, `engine/` skeleton (4 subpackages),
  `closedSpace.map.dump` (ISC-5 ✓), `Makefile` with `make all` green
  (ruff clean, mypy strict clean, 25 tests pass).
- **Phase 1 complete (2026-05-13):** `closedSpace/mission/` package
  with pure `plan(map, config) → MissionPlan`. ISC-6 through ISC-10
  all `[x]`. Reference fixture produces 70 waypoints (64 captures),
  path length 118.0316 m matches hand-derived reference to 4 decimals,
  est duration 310 s ≪ 900 s cap. Spec ambiguity in §10.2 vs §10.2.3.2
  resolved in favor of §10.2.2 "minimum transit" intent: racks visited
  in entry-direction physical order (reversed on alternate aisles).
  Documented in `closedSpace/mission/plan.py` module docstring.
- **Phase 2 complete (2026-05-13):** `engine/` Protocols filled in.
  `SLAMProvider`/`GPSProvider` (engine.localization), `FlightController`
  + state machine (engine.flight_control), pub/sub bus + JSONL logger
  (engine.telemetry), `Camera` + stdlib Laplacian focus score
  (engine.sensors), `SimWorld`/`SimSLAM`/`SimFlightController`/`SimCamera`
  in-process stubs (engine.sim). ISC-11, ISC-30, ISC-36 flipped.
  Anti-bleed test uses AST import scan, not substring grep.
  Integration smoke at `closedSpace/tests/mission/test_sim_integration.py`
  exercises the Phase 2 exit criterion: plan → sim end-to-end, final
  state DISARMED, 64 captures, lifecycle transitions logged to JSONL.
- **Phase 4 complete (2026-05-13):** `closedSpace/capture/`,
  `closedSpace/storage/`, `closedSpace/report/` + schema. CaptureSink
  runs resolution + focus gates, builds §ISC-17 sidecars, §ISC-18
  filename pattern. LocalSink does fsync + atomic-rename so each
  capture is durable before the next waypoint. RemoteSink Protocol +
  `sync_to_remote` retains local data on failure and writes
  `.sync-pending` markers. ReportBuilder accumulates outcomes, emits
  schema-valid `mission_report.json` with exact coverage arithmetic.
  ISC-16, 17, 18, 21, 22, 23, 24, 25, 32 flipped (9 ISCs). ISC-19 /
  ISC-20 stay open — gate logic implemented and tested but real-
  hardware threshold verification is Phase 8. End-to-end test
  `closedSpace/tests/test_mission_e2e.py` drives reference plan
  through the full stack: 64 .jpg + 64 .jpg.json on disk,
  coverage_pct = 100.0, schema valid.
- **Phase 5 complete (2026-05-13):** `closedSpace/operator/` package
  (`PreflightChecklist`, `MissionRunner`, `AbortSignal`) + `closedSpace/run.py`
  CLI shim. Preflight runs five checks (battery, calibration, takeoff
  in coverage, free pad, map staleness) with per-item PASS/FAIL/WARN.
  MissionRunner polls abort before every waypoint and publishes
  `mission.started`/`mission.progress`/`mission.finished` events.
  CLI prints plan summary, runs preflight, prompts for explicit
  "yes" confirmation, writes report. ISC-26, 27, 28, 29, 34, 44
  flipped (6 ISCs). ISC-42 antecedent: `docs/operator-README.md`
  in place; the "warehouse staffer in 15 min" verification is a
  Phase 8 pilot deliverable.

## What's open

- **D1**: sim-first vs hardware-first (recommended: sim-first).
- **D2**: simulator choice (recommended: two-tier — in-process
  kinematic now + Gazebo/PX4-SITL later).
- **D3**: flight stack (recommended: defer; `engine.flight_control`
  Protocol abstracts it).

## Suggested first move on resume

**Phase 6 — Quality gates polish** (~2–3 days). Most of Phase 6 is
already met by `make all` (ruff clean, mypy strict clean — ISC-38,
ISC-39). Three items remain:
* Coverage report ≥ 80 % on `closedSpace/` (ISC-37) — add coverage
  to Makefile and verify.
* Docstring lint (ISC-40) — pick / write a tool that catches the
  "every public function has an OpenSpec docstring" rule.
* Test-file-pair lint (ISC-41) — enforce that every new source file
  has a corresponding test file.

Phase 3 still waits on D1/D2. Phase 7 (MapBuilderFromWMS) is the
pilot-deployment unblocker but is independent of v1 flight scope.
Phase 8 (real-hardware pilot) is the home for the still-open ISCs
19, 20, 27 (hardware tightening), 31, 33, 42.

---

## Cross-doc map

| If you want… | Read |
|---|---|
| The verifiable contract — what "done" means | `ISA.md` |
| A walkthrough from the operator's point of view | `docs/use-cases.md` |
| What to build next, in order | `docs/next-steps.md` |
| The warehouse-map data model + path derivation | `docs/map-schema.md` |
| Drone hardware + software + cost + accessories | `docs/drones.md` |
| The implemented loader + validator | `closedSpace/map/` |
| The reference fixture (and the path-length probe target) | `closedSpace/tests/fixtures/maps/reference_warehouse.yaml` |
| The machine-checkable schema | `closedSpace/schemas/map.schema.json` |

---

*Refresh this file at the start and end of each session; it should
remain a one-screen pickup point.*
