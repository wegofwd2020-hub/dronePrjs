# closedSpace — Use Cases (v1)

> Companion to `ISA.md`. The ISA is the verifiable contract; this
> document is the human-readable narrative of what the system *does*
> from each actor's point of view. Every use case maps back to specific
> Features and ISCs in the ISA, so a reader can pivot from "tell me a
> story" to "show me the probe" in one hop.

---

## At-a-glance inventory

| ID | Use case | Status | Primary actor |
|---|---|---|---|
| UC-1 | Run a warehouse inventory mission | In v1 | Warehouse operator |
| UC-2 | Load and validate a warehouse map | In v1 — DONE | Mission system |
| UC-3 | Refuse to fly a stale or malformed map | In v1 — partial | Mission preflight |
| UC-4 | Build a warehouse map from operator systems | Sketched | Surveyor / IT engineer |
| UC-5 | Capture an image at a shelf position | In v1 | Drone (sub-flow of UC-1) |
| UC-6 | Survive ground-station link loss | In v1 | Drone autonomy |
| UC-7 | Survive SLAM tracking loss | In v1 | Drone autonomy |
| UC-8 | Produce a post-mission coverage report | In v1 | Mission system |
| UC-9 | Re-survey after warehouse layout change | Operational | Operator + surveyor |

Status legend:
- **In v1** — explicitly in scope of v1 ISA
- **DONE** — implementation shipped and verified by smoke runner
- **partial** — some ISCs verified, others pending implementation
- **Sketched** — Feature recorded in ISA, no code yet
- **Operational** — process / runbook, no in-flight code

---

## UC-1: Run a warehouse inventory mission

**Primary actor:** Warehouse operator (non-pilot trained staff).
**Goal:** Capture metadata-tagged images of every shelf level on every
declared rack in the warehouse, autonomously, in one mission.
**Status:** In v1 — primary use case.
**Maps to features:** `MissionPlanner`, `LocalizationAndControl`,
`CaptureSubsystem`, `StorageAndSync`, `MissionReport`, `OperatorConsole`.
**Maps to ISCs:** ISC-6 … ISC-29, ISC-42 (antecedent).

### Preconditions

- A validated YAML map exists for the warehouse (UC-2 has succeeded).
- Drone battery is charged above pre-flight threshold.
- Warehouse floor inside the coverage polygon is clear of personnel.
- The operator has authority to fly during the scheduled window.

### Main flow

1. Operator runs `python -m closedSpace.run --map <map.yaml>`.
2. System loads and validates the map (UC-2).
3. System runs the pre-flight checklist (battery, calibration, map
   signature, free-space, takeoff pad inside coverage, map staleness
   per UC-3).
4. System prints a plan summary — total waypoints, capture count,
   estimated duration, route — and waits for explicit operator
   confirmation.
5. Drone arms and takes off from the takeoff pad to
   `TAKEOFF_HEIGHT_M`.
6. For each aisle in declared order (boustrophedon when
   `direction: any`):
   1. Drone transits to the entry end at `AISLE_TRAVERSAL_HEIGHT_M`.
   2. For each side (`west` then `east`), each rack in
      `position_along` order, each level in `index` order: drone
      navigates to the capture pose, holds, runs UC-5 (capture), and
      advances.
   3. Drone transits out at the opposite end.
7. Drone routes to the next aisle's entry via free-space corridor at
   `AISLE_TRAVERSAL_HEIGHT_M`, avoiding no-go zones.
8. After the last aisle, drone returns to the takeoff pad and lands.
9. Captures sync to the configured backend (post-flight).
10. System emits `mission_report.json` (UC-8).

### Alternate flows

- **Pre-flight fails** → arm blocked, item-by-item failure report
  printed, operator addresses cause and reruns.
- **Operator presses abort key** → drone transitions to `LAND_NOW`
  within 500 ms (ISC-27).
- **Ground-station link drops mid-flight** → UC-6.
- **SLAM tracking lost mid-flight** → UC-7.
- **Local storage fills mid-mission** → drone aborts, returns home,
  surfaces the error.

### Postconditions

- Mission report on disk with `coverage_pct` and an enumerated
  `missed_waypoints` list.
- Captured images at
  `{warehouse_id}/{aisle_id}/{rack_id}/{level_index}/{timestamp}.jpg`.
- Drone disarmed on the takeoff pad (or safely on ground per UC-6 / UC-7).

---

## UC-2: Load and validate a warehouse map

**Primary actor:** Mission system (called by UC-1 step 2 and by UC-4).
**Goal:** Parse a YAML map and produce a validated typed `Map`, or fail
fast with a precise, actionable error.
**Status:** In v1 — **DONE**. Loader + validator implemented; 22-case
smoke runner passes against the reference fixture.
**Maps to features:** `MapSchemaAndLoader`.
**Maps to ISCs:** ISC-1 ✓, ISC-2 ✓, ISC-3 ✓, ISC-4 ✓, ISC-5 (pending —
dump round-trip).

### Preconditions

- Caller supplies a filesystem path to a YAML file.

### Main flow

1. `closedSpace.map.load(path)` opens the file and runs
   `yaml.safe_load`.
2. Loader confirms the parsed root is a mapping.
3. `validate(data)` runs in three layers:
   1. Version — reject if `schema_version` is not in
      `SUPPORTED_MAP_VERSIONS`.
   2. Schema — reject any structural violation per
      `schemas/map.schema.json`.
   3. Semantics — reject any of the 12 geometric / consistency
      violations (polygon simplicity, takeoff in coverage, aisle
      width vs clearance, rack extent inside centerline, centerline
      not crossing a no-go zone, id uniqueness, level-index
      monotonicity, …).
4. Loader builds frozen typed dataclasses and returns the `Map`.

### Alternate flows

| Failure | Exception | Notes |
|---|---|---|
| File not found | `MapError` | Message includes the path |
| Bad YAML | `MapError` | Message includes the YAML parser detail |
| Non-mapping root | `MapValidationError` | `field='<root>'` |
| Unsupported `schema_version` | `UnsupportedMapVersionError` | `.version` carries the offending value |
| Schema violation | `MapValidationError` | `.field` is the dotted path of the offender |
| Semantic violation | `MapValidationError` | `.field` names the offender; message names the rule |

### Postconditions

- Either a validated, immutable `Map` object is returned to the caller,
- or a typed exception with diagnostic detail is raised.

---

## UC-3: Refuse to fly a stale or malformed map

**Primary actor:** Mission preflight (orchestrated by `OperatorConsole`).
**Goal:** Block flight on an outdated, invalid, or misaligned map;
surface the precise reason; route the operator to remediation.
**Status:** In v1 — partial. Load-time validation is DONE (UC-2);
staleness and arm-blocking checks are pending.
**Maps to features:** `MapSchemaAndLoader` (load-time),
`OperatorConsole` (preflight).
**Maps to ISCs:** ISC-30 … ISC-36 (anti-criteria), ISC-43 ✓ (loader
carries provenance), ISC-44 (anti — preflight refuses stale maps).

### Preconditions

- Operator has initiated UC-1.
- Map file exists at the supplied path.

### Main flow

1. UC-2 runs end-to-end. If it raises, preflight aborts; CLI prints
   the exception message; operator is advised on remediation.
2. Preflight checks `Map.surveyed_at`:
   - `None` → emit non-blocking warning ("map provenance unknown").
   - `today - surveyed_at > MAX_MAP_AGE_DAYS` (default 30) AND
     `--allow-stale-map` not set → preflight aborts with a stale-map
     error naming `surveyed_at` and `MAX_MAP_AGE_DAYS`.
3. Preflight runs the remaining checklist items: battery, calibration,
   takeoff pad inside coverage, free-space at takeoff pad, drone
   parked within `takeoff_pad.radius_m`.
4. If all checks pass, preflight authorizes UC-1 step 5 (arm + takeoff).

### Alternate flows

- Operator passes `--allow-stale-map` → preflight emits a stronger
  warning, proceeds.
- Drone is not parked at the takeoff pad → arm blocked (ISC-34).

### Postconditions

- Either flight is authorized,
- or operator has an actionable diagnostic and the system remains in
  a safe (un-armed) state.

---

## UC-4: Build a warehouse map from operator systems

**Primary actor:** Surveyor / IT engineer, during initial deployment or
after layout change.
**Goal:** Produce a validated YAML map by combining sources warehouses
already have — WMS export, architectural drawings, rack vendor specs, a
half-day site survey — instead of authoring YAML by hand.
**Status:** Sketched. Feature `MapBuilderFromWMS` recorded in the ISA;
no implementation yet.
**Maps to features:** `MapBuilderFromWMS`.
**Maps to ISCs:** ISC-43 (provenance carried into output map).

### Preconditions

- WMS export available in a supported format (CSV/JSON for SAP EWM,
  Manhattan Active WM, Fishbowl — adapter list grows over time).
- Architectural drawing available (DWG / DXF / IFC).
- Rack vendor spec on hand for the rack product line in use.
- A short survey overlay: aisle centerline endpoints, takeoff pad
  position, any rack-position deltas where the floor plan disagrees
  with the as-built state.

### Main flow

1. Engineer runs:
   ```bash
   closedSpace map from-wms \
     --wms <export> --floorplan <dwg> \
     --rack-spec <spec> --survey <overlay> \
     --warehouse-id <id> \
     --surveyed-by "<org>" --surveyed-at <YYYY-MM-DD> \
     --out <map.yaml>
   ```
2. Builder reads the WMS export → logical aisle / rack / level
   structure.
3. Builder reads the floor plan → coverage polygon and no-go zones
   (columns, fixtures).
4. Builder reads the rack spec → level heights and rack lengths
   keyed by rack model.
5. Builder reads the survey overlay → centerline coordinates,
   takeoff pad, per-rack offset corrections.
6. Builder composes a v1 map dict with `surveyed_at` /
   `surveyed_by` populated.
7. Builder runs `closedSpace.map.validate.validate(...)` — abort on
   any failure.
8. Builder writes YAML to `<out>`.
9. Builder prints a diff against any prior map at the same path so
   the engineer can review changes before adopting.

### Alternate flows

- WMS missing a level for a rack referenced by the rack spec →
  builder errors with the rack id and missing level index.
- Floor plan polygon has self-intersections → builder errors with
  the offending edge indices (delegates to the same simplicity check
  the validator uses).
- Survey overlay disagrees with the floor plan beyond a tolerance →
  builder warns; engineer resolves.

### Postconditions

- New YAML on disk, validated, ready for UC-1.
- Provenance fields populated for staleness tracking (UC-3).

---

## UC-5: Capture an image at a shelf position

**Primary actor:** Drone (autonomous sub-flow of UC-1 step 6.b).
**Goal:** Capture exactly one focused, well-lit photograph at each
declared shelf level, with a sidecar metadata record.
**Status:** In v1 — pending implementation.
**Maps to features:** `CaptureSubsystem`, `StorageAndSync`.
**Maps to ISCs:** ISC-16 … ISC-20, ISC-32 (anti — silent data loss).

### Preconditions

- Drone is at the planned capture pose for `(aisle_id, rack_id, level_index)`.
- Camera is calibrated; lens is unobstructed.
- Local persistent storage has free space ≥ buffer threshold.

### Main flow

1. Drone holds pose ≥ `CAPTURE_HOLD_MS`.
2. Camera captures one frame.
3. System computes a Laplacian-variance focus score.
4. If `focus_score < MIN_FOCUS_SCORE`, capture is recorded as a
   soft-fail (still saved, flagged in mission report).
5. Image is written to local persistent storage at
   `{warehouse_id}/{aisle_id}/{rack_id}/{level_index}/{timestamp}.jpg`.
6. Sidecar JSON is written with `aisle_id, rack_id, level_index,
   pose {x,y,z,yaw}, timestamp_utc, mission_id, image_uri`.
7. Drone advances to the next waypoint.

### Alternate flows

- Local storage fills → drone aborts mission, RTH per UC-6 alternate.
- Camera fault → capture marked missed in mission report; drone
  continues if other levels are still reachable, else aborts.

### Postconditions

- Image and sidecar on local storage.
- Capture counter incremented in mission state.

---

## UC-6: Survive ground-station link loss

**Primary actor:** Drone autonomy.
**Goal:** Complete the mission, or land safely, even if the ground-
station link drops mid-flight.
**Status:** In v1 — pending implementation.
**Maps to features:** `LocalizationAndControl`, `OperatorConsole`.
**Maps to ISCs:** ISC-15, ISC-27.

### Preconditions

- Drone is mid-mission.
- Ground station was previously linked.

### Main flow

1. Comms link drops.
2. Drone notices `time_since_last_heartbeat > LINK_LOSS_TIMEOUT_S`
   (default 5 s).
3. Drone transitions to `RETURN_TO_HOME`.
4. Drone routes to the takeoff pad at `AISLE_TRAVERSAL_HEIGHT_M`,
   avoiding no-go zones.
5. Drone descends and lands on the pad.

### Alternate flows

- Link returns before timeout → drone resumes mission.
- Link returns mid-RTH → drone *continues* RTH (does not auto-resume,
  by design — operator must explicitly re-authorize).

### Postconditions

- Drone landed safely (or in `SAFE_HOVER` if RTH is blocked).
- Mission report records the link-loss event and the last completed
  waypoint.

---

## UC-7: Survive SLAM tracking loss

**Primary actor:** Drone autonomy.
**Goal:** Avoid uncommanded drift when visual-inertial localization
diverges; recover or land safely.
**Status:** In v1 — pending implementation.
**Maps to features:** `LocalizationAndControl`.
**Maps to ISCs:** ISC-12.

### Preconditions

- Drone is mid-mission.
- SLAM provider has been publishing pose with acceptable confidence.

### Main flow

1. SLAM provider's confidence drops below threshold or tracking is
   lost.
2. Within ≤ 200 ms, drone transitions to `SAFE_HOVER` — zero-velocity
   hold based on the last-known good pose.
3. Drone attempts SLAM re-acquisition for ≤ `SLAM_RECOVERY_TIMEOUT_S`.
4. If recovered, drone resumes mission from current pose.
5. If not recovered, drone descends in place at low rate to a
   controlled landing.

### Alternate flows

- Operator presses abort during `SAFE_HOVER` → land-now.

### Postconditions

- Drone safely on ground.
- Mission report records the SLAM-loss event and the final pose.

---

## UC-8: Produce a post-mission coverage report

**Primary actor:** Mission system (after the drone disarms).
**Goal:** Emit a single auditable JSON document covering every aspect
of the just-completed mission.
**Status:** In v1 — pending implementation.
**Maps to features:** `MissionReport`.
**Maps to ISCs:** ISC-23, ISC-24, ISC-25.

### Preconditions

- A mission has terminated (success or otherwise).
- Telemetry log + capture index are available.

### Main flow

1. Aggregator collects: planned waypoints, captured waypoints,
   missed waypoints with reasons, telemetry summary, total duration,
   any link-loss / SLAM-loss / abort events.
2. Computes `coverage_pct = captured / planned × 100`.
3. Writes `mission_report.json` matching
   `schemas/mission_report.schema.json`.
4. Validates the report against its schema before declaring the
   mission complete.

### Alternate flows

- Mission aborted before any capture → report still emitted with
  `coverage_pct: 0` and an `abort_reason` field populated.

### Postconditions

- `mission_report.json` on disk.
- Operator can review without consulting any other artifact.

---

## UC-9: Re-survey after warehouse layout change

**Primary actor:** Operator + surveyor (operational, not in-flight).
**Goal:** Refresh the map's `surveyed_at` and any geometry that
changed, so subsequent missions don't fly into outdated geometry.
**Status:** Operational — process and spec only; no in-flight code
needed beyond UC-3 + UC-4.
**Maps to features:** `MapBuilderFromWMS` (re-run); UC-3 enforces.
**Maps to ISCs:** ISC-43, ISC-44.

### Preconditions

- Warehouse layout changed (rack moved / added / removed; column
  added; aisle reorganized).
- The current map's `surveyed_at` no longer reflects reality.

### Main flow

1. Operations notifies the drone team of the layout change.
2. Surveyor re-measures the affected aisles / racks (full warehouse
   not always required).
3. Engineer re-runs UC-4 with updated WMS export, drawing, and survey
   overlay; new `surveyed_at` and `surveyed_by` are stamped on the
   output.
4. New YAML replaces the old one (or sits alongside as a versioned
   successor).
5. Pre-flight gate (UC-3) sees a fresh `surveyed_at`; missions resume.

### Alternate flows

- **Partial change** (one rack moved) → engineer hand-edits the
  offending rack rather than running a full re-survey, re-validates,
  bumps `surveyed_at`.
- **Re-survey detected by drone in flight** (future feature) → drone
  flags the discrepancy in the mission report; mission continues if
  geometry change is non-blocking, else aborts.

### Postconditions

- Map matches reality.
- `MAX_MAP_AGE_DAYS` clock resets.

---

## Cross-reference table

| Use case | Features | ISCs | Status |
|---|---|---|---|
| UC-1 Run mission | MissionPlanner, LocalizationAndControl, CaptureSubsystem, StorageAndSync, MissionReport, OperatorConsole | 6–29, 42 | In v1 |
| UC-2 Load + validate map | MapSchemaAndLoader | 1–5 (1–4 ✓) | DONE |
| UC-3 Preflight refusal | MapSchemaAndLoader, OperatorConsole | 30–36, 43 ✓, 44 | In v1, partial |
| UC-4 Build from WMS | MapBuilderFromWMS | 43 ✓ | Sketched |
| UC-5 Capture image | CaptureSubsystem, StorageAndSync | 16–20, 32 | In v1 |
| UC-6 Link loss | LocalizationAndControl, OperatorConsole | 15, 27 | In v1 |
| UC-7 SLAM loss | LocalizationAndControl | 12 | In v1 |
| UC-8 Coverage report | MissionReport | 23–25 | In v1 |
| UC-9 Re-survey | MapBuilderFromWMS (re-run); UC-3 enforces | 43, 44 | Operational |

---

## Where to look next

- `ISA.md` for the verifiable contract — Goal, Criteria, Test Strategy,
  Features, Decisions.
- `docs/map-schema.md` for the warehouse-map data model + path-derivation
  contract.
- `tests/fixtures/maps/reference_warehouse.yaml` for the reference
  geometry used by UC-2 verification.
- `closedSpace/map/` for the implemented loader + validator (UC-2).
