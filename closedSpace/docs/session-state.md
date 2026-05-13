# Session State — closedSpace

> Pickup point. Read this first when resuming work; it points at the
> four canonical sources for everything we know about the project.

**Last updated:** 2026-05-13
**Current phase:** observe (project ISA `phase: observe`, `progress: 14/44`)
**Roadmap:** Phases 0, 1, 2 complete. closedSpace runs end-to-end against
the in-process sim. D1–D3 still gate Phase 3 simulator bring-up. Next
unblocked chunk: Phase 4 (Capture + Storage + Report).

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

## What's open

- **D1**: sim-first vs hardware-first (recommended: sim-first).
- **D2**: simulator choice (recommended: two-tier — in-process
  kinematic now + Gazebo/PX4-SITL later).
- **D3**: flight stack (recommended: defer; `engine.flight_control`
  Protocol abstracts it).

## Suggested first move on resume

**Phase 4 — Capture + Storage + Report** (~4–6 days). Phase 3 is
decision-gated (D1/D2 not yet answered); Phase 4 isn't. Build the
real mission runner that wires the plan to the sim Protocols, writes
captured frames + metadata sidecars to a per-mission directory, and
emits a `mission_report.json`. Satisfies ISC-16 through ISC-25 plus
the anti-data-loss ISC-32.

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
