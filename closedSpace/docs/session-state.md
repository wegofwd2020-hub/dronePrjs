# Session State — closedSpace

> Pickup point. Read this first when resuming work; it points at the
> four canonical sources for everything we know about the project.

**Last updated:** 2026-05-13
**Current phase:** observe (project ISA `phase: observe`, `progress: 35/44`)
**Roadmap:** Phases 0, 1, 2, 4, 5, 6 complete. Full quality gate
auditable in CI: coverage ≥ 80 % (actual 95 %), mypy strict clean,
ruff + docstring lint clean, anti-scope-creep AST scan, file-pair
lint, GitHub Actions workflow on PR. D1–D3 still gate Phase 3
simulator bring-up. Remaining v1 work is Phase 7 (MapBuilderFromWMS,
pilot-deployment scope) and Phase 8 (real-hardware pilot — home for
ISC-19, 20, 27 tightening, 31, 33, 42).

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
- **Phase 6 complete (2026-05-13):** quality gates auditable in CI.
  pytest-cov with `--cov-fail-under=80` (actual 95 %), ruff D101–D104
  docstring rules enabled, AST-based anti-scope-creep scan rejects
  cv2/torch/easyocr/etc imports under closedSpace/, file-pair lint
  enforces test mirrors, `.github/workflows/ci.yml` runs `make all` on
  PR + main push. ISC-35, 37, 38, 39, 40, 41 flipped (6 ISCs).

## What's open

- **D1**: sim-first vs hardware-first (recommended: sim-first).
- **D2**: simulator choice (recommended: two-tier — in-process
  kinematic now + Gazebo/PX4-SITL later).
- **D3**: flight stack (recommended: defer; `engine.flight_control`
  Protocol abstracts it).

## Suggested first move on resume

Remaining v1 work splits into three independent tracks:

* **Phase 3 (Simulator bring-up)** still gated on D1 (sim-vs-hardware)
  and D2 (which sim). Until those are answered, this phase doesn't
  start — the in-process sim is sufficient for everything Phase 0–6
  built.
* **Phase 7 (MapBuilderFromWMS)** — out of v1 *flight* scope but on
  the v1 *deployment* path. Without it, every new warehouse needs a
  hand-rolled YAML map. ~5–10 days.
* **Phase 8 (Pilot mission)** — real-hardware reference run. Home for
  the still-open ISCs: 19 (≥ 4 MP), 20 (focus pass rate), 27
  (abort latency on real hardware with long dwells), 31 (anti-
  collision), 33 (clearance enforcement), 42 (operator antecedent
  verification with a non-pilot).

In code-only terms, **v1 is functionally complete**: the closedSpace
mission planner, sim runner, capture/storage/report pipeline, and
operator CLI all run end-to-end with full quality gates enforced.

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
