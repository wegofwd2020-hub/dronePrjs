# Session State — closedSpace

> Pickup point. Read this first when resuming work; it points at the
> four canonical sources for everything we know about the project.

**Last updated:** 2026-05-03 (paused)
**Current phase:** observe (project ISA `phase: observe`, `progress: 5/44`)

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
  22-case smoke runner passes against the reference fixture.
- Optional provenance fields (`surveyed_at`, `surveyed_by`) added in
  schema v1, threaded through loader, ISC-43 verified.
- pyproject.toml at project root with pytest config + deps declared.
- Use cases + roadmap + drone survey all written under `docs/`.

## What's open

- **D1**: sim-first vs hardware-first (recommended: sim-first).
- **D2**: simulator choice (recommended: two-tier — in-process
  kinematic now + Gazebo/PX4-SITL later).
- **D3**: flight stack (recommended: defer; `engine.flight_control`
  Protocol abstracts it).
- ISC-5 (map dump round-trip) — last loose end on the loader.
- pytest is not yet installed in the local Python; smoke runner is
  the workaround. Phase 0 fixes this.

## Suggested first move on resume

**Phase 0 — Foundations** (~1–2 days). Tasks NS-0.1 through NS-0.6 in
`docs/next-steps.md`:

1. Create venv at `dronePrjs/.venv`, `pip install -e .[dev]`.
2. Init git repo, commit current state.
3. Add `.gitignore` (`__pycache__`, `.venv`, `.pytest_cache`).
4. Scaffold `engine/` skeleton (empty modules).
5. Implement ISC-5 (`closedSpace.map.dump`) + test.
6. Add a `Makefile` with `test`, `lint`, `typecheck`, `all`.

After Phase 0, **MissionPlanner (Phase 1)** is the next clean 3–5
day chunk against the path-derivation contract in
`docs/map-schema.md` §10.

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
