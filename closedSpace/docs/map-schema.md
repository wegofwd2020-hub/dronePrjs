# Warehouse Map Schema (v1.0)

> Status: spec — implementation pending. This document defines the contract
> the map producer, the validator, and the mission planner all agree on.
> Machine-validated against `schemas/map.schema.json`.

---

## 1. Purpose

A warehouse map is the only authoritative source of geometry that
`closedSpace` consumes during a mission. Everything the drone does — where
to fly, how high to climb, what to capture, what to avoid — is derived from
this file. The drone never invents geometry it was not given.

A map describes:

1. The **reference frame** (origin, axes, units).
2. The **flyable region** (coverage polygon).
3. The **takeoff pad**.
4. The **aisles** the drone may traverse.
5. The **racks** on each side of each aisle, and the **shelf levels** on each rack.
6. The **no-go zones** (columns, fixtures, wires) that must be avoided.

A map does **not** describe inventory, SKUs, bin contents, or anything the
drone learns during the mission.

---

## 2. Reference frame

- Right-handed, axis-aligned: `+x` east, `+y` north, `+z` up.
- Origin is the southwest corner of the warehouse floor at floor level.
- Units are **meters** (`units: meters` is the only allowed value in v1).
- Yaw is measured in **degrees**, counterclockwise from `+x` (east).

All coordinates in a map are in this frame. The drone's localization stack
publishes poses in the same frame after a one-time alignment at the
takeoff pad.

---

## 3. Top-level structure

```yaml
schema_version: "1.0"        # required; only "1.0" supported in v1
warehouse_id: "wh-01"        # required; stable id for downstream pipelines
units: meters                # required; only "meters" supported in v1

coverage_polygon: [...]      # required; convex or simple polygon in (x, y)
takeoff_pad: {...}           # required
no_go_zones: [...]           # optional; default empty
aisles: [...]                # required; ≥1 aisle

# Provenance / staleness — optional, recommended.
surveyed_at: "2026-04-15"    # ISO-8601 date the map was last surveyed
surveyed_by: "ACME Surveys / facilities@warehouse.example"
```

### 3.1 Staleness

Warehouses re-rack. A map drifts from reality the moment the next pallet
moves. The schema carries provenance — `surveyed_at` and `surveyed_by` —
so the mission planner's pre-flight gate can reject maps older than a
configured `MAX_MAP_AGE_DAYS` and route the operator to re-survey before
flying. Both fields are **optional** in v1 to avoid breaking maps that
predate the convention; the loader returns them as `None` when absent
and the pre-flight gate treats `None` as a soft warning rather than a
hard block (configurable).

`surveyed_at` is a date string in `YYYY-MM-DD` format. Time of day is
deliberately not modeled — surveys are scoped to a calendar day.

A map is **rejected at load time** if any required field is missing or any
field violates the schema. See section 9.

---

## 4. Coverage polygon

The closed polygon (in the floor plane) inside which the drone may fly.
Anything outside this polygon — including the airspace above it — is
forbidden. Used at arm time: if the takeoff pad does not lie inside this
polygon, the drone refuses to arm (ISC-34).

```yaml
coverage_polygon:
  - [0.0,  0.0]
  - [12.0, 0.0]
  - [12.0, 8.0]
  - [0.0,  8.0]
```

Vertices are listed in order (either winding direction). The polygon must
be **simple** (non-self-intersecting). It does not have to be convex.

---

## 5. Takeoff pad

Where the drone arms, takes off, and lands.

```yaml
takeoff_pad:
  position: [1.0, 1.0, 0.0]   # x, y, z in meters
  yaw_deg: 0                  # facing direction at arm
  radius_m: 0.5               # geofenced "home" zone
```

The mission's first and last waypoint are always at this position.
Clearance enforcement is relaxed inside this radius — it is the only place
the drone may legally come within `MIN_CLEARANCE_M` of the floor.

---

## 6. No-go zones

Columns, racking we don't yet trust to fly near, suspended fixtures, etc.
A no-go zone is a 2D polygon with a vertical extent.

```yaml
no_go_zones:
  - id: "support_column_a"
    polygon:
      - [5.5, 4.0]
      - [5.7, 4.0]
      - [5.7, 4.2]
      - [5.5, 4.2]
    z_min: 0.0
    z_max: 6.0
```

Planner rule: no waypoint may lie inside the (polygon × [z_min, z_max])
prism. Inter-aisle transitions must route around no-go zones (ISC-10).

---

## 7. Aisles

An aisle is a corridor with shelving on one or both sides. The drone
traverses each declared aisle once per mission, capturing every shelf
level on every rack on every side.

```yaml
aisles:
  - id: "A1"
    centerline:
      start: [3.0, 1.5]      # entry-end midpoint
      end:   [3.0, 6.5]      # exit-end midpoint
    width_m: 2.4              # full aisle width
    direction: any            # any | north_to_south | south_to_north | etc.
    racks:
      west: [...]             # racks on the -x side of centerline (when aisle runs N-S)
      east: [...]             # racks on the +x side
```

### 7.1 Centerline

Two points defining the line the drone flies along when traversing.
The drone's `(x, y)` while traversing is on this line; only `z` and yaw
change between captures.

The line must lie entirely inside the coverage polygon and must not pass
through any no-go zone.

### 7.2 Width

The full aisle width (rack-face to rack-face). The minimum-clearance
constraint (`MIN_CLEARANCE_M = 0.5`) means `width_m ≥ 2 × MIN_CLEARANCE_M
+ drone_envelope_m`. Maps that violate this are rejected.

### 7.3 Direction

`direction` controls traversal ordering across aisles:

| value | meaning |
|---|---|
| `any` | planner chooses to minimize total path length (default boustrophedon) |
| `north_to_south` | drone always enters at the north end |
| `south_to_north` | drone always enters at the south end |
| `east_to_west` / `west_to_east` | for east-west-running aisles |

### 7.4 Sides

`west` and `east` are used for north-south aisles; `north` and `south` for
east-west aisles. Either side may be omitted (single-sided aisle). At
least one side must have ≥1 rack.

---

## 8. Racks and levels

```yaml
racks:
  west:
    - id: "A1-W1"
      position_along: 0.6     # meters from centerline.start
      length_m: 1.2           # extent along aisle
      face_offset_m: 0.6      # capture distance from rack face (drone-to-face)
      yaw_deg: 270            # drone yaw to face this rack (here: facing west)
      levels:
        - { index: 0, height_m: 0.5 }
        - { index: 1, height_m: 1.5 }
        - { index: 2, height_m: 2.5 }
        - { index: 3, height_m: 3.5 }
```

### 8.1 Rack fields

| field | meaning |
|---|---|
| `id` | stable id, unique within the map; appears in image filenames |
| `position_along` | distance from `centerline.start` to rack mid-point |
| `length_m` | rack extent along the aisle |
| `face_offset_m` | drone's perpendicular distance from rack face during capture; must satisfy `face_offset_m ≥ MIN_CLEARANCE_M` |
| `yaw_deg` | absolute yaw the drone holds while capturing this rack |
| `levels` | ordered list of shelf levels |

### 8.2 Levels

| field | meaning |
|---|---|
| `index` | integer, monotonically increasing per rack (0 = lowest) |
| `height_m` | center height of the level above floor; capture pose `z` = this value |

A level may declare `bays` (sub-divisions along rack length) in a future
schema version; v1 captures one image per (rack, level).

---

## 9. Validation rules

A loader (`closedSpace.map.load(path)`) MUST reject a map if any of the
following hold:

1. `schema_version` is not in the supported set (`{"1.0"}` for v1) →
   `UnsupportedMapVersionError`.
2. Any required field is missing or has the wrong type →
   `MapValidationError(field=...)`.
3. `units` is not `"meters"`.
4. The coverage polygon is not simple, or has < 3 vertices.
5. The takeoff pad does not lie inside the coverage polygon.
6. Any aisle's centerline endpoints lie outside the coverage polygon.
7. Any aisle width violates the clearance constraint
   (`width_m < 2 × MIN_CLEARANCE_M + drone_envelope_m`).
8. Any rack's `face_offset_m < MIN_CLEARANCE_M`.
9. Any rack's `position_along` plus half its `length_m` falls outside
   the centerline's length.
10. Any level's `height_m` is non-positive or exceeds the warehouse
    ceiling height (declared via `MAX_FLIGHT_ALTITUDE_M` in mission
    config; not in the map itself).
11. Any rack id, aisle id, or no-go-zone id is duplicated.
12. Any centerline passes through a no-go zone.

The full machine-checkable contract is `schemas/map.schema.json`.

---

## 10. Path-derivation contract

Given a valid map M, `closedSpace.mission.plan(M)` MUST produce a
`MissionPlan` according to these rules:

### 10.1 Waypoint definition

A **waypoint** is a 6-tuple
`(x, y, z, yaw_deg, capture: bool, metadata)` where:
- `(x, y, z)` is the drone pose in the map frame
- `yaw_deg` is the absolute yaw to hold
- `capture = true` means the drone pauses and captures one image at this pose
- `metadata` carries `{aisle_id, rack_id, level_index}` for capture
  waypoints, or `{kind: "transit" | "takeoff" | "landing"}` otherwise

### 10.2 Algorithm

1. **Takeoff waypoint** — at `takeoff_pad.position` lifted to a configured
   `TAKEOFF_HEIGHT_M`. `capture = false`.

2. **Aisle ordering** — for each aisle in declared order:
   - If `direction = any`, alternate entry end (boustrophedon) so consecutive
     aisles share an end point and total transit is minimized.
   - Otherwise, enter at the side dictated by `direction`.

3. **Per aisle** — at the chosen entry end:
   1. Insert a **transit-in** waypoint at
      `(entry_end_x, entry_end_y, AISLE_TRAVERSAL_HEIGHT_M)` with
      `capture = false`.
   2. For each side of the aisle in a fixed order (west then east, or
      south then north), and for each rack on that side in declared
      `position_along` order:
      - For each level in `index` order:
        - Compute capture pose:
          - `(x, y)` = centerline point at `rack.position_along`,
            offset perpendicular to centerline by
            `(width_m / 2 - face_offset_m)` toward the rack side
          - `z` = `level.height_m`
          - `yaw_deg` = `rack.yaw_deg`
        - Emit waypoint with `capture = true` and metadata
          `{aisle_id, rack_id, level_index}`.
   3. Insert a **transit-out** waypoint at the opposite end of the
      centerline at `AISLE_TRAVERSAL_HEIGHT_M`.

4. **Inter-aisle transition** — between consecutive aisles, route the
   drone via free-space corridors at `AISLE_TRAVERSAL_HEIGHT_M`,
   avoiding no-go zones. The corridor router is out of scope for this
   document; this contract requires only that the resulting path does
   not enter any no-go zone (ISC-10).

5. **Landing waypoint** — return to `takeoff_pad.position` at
   `TAKEOFF_HEIGHT_M`, then descend.

### 10.3 Per-mission tunables (not in the map)

These come from mission config, not the map:

| name | default | meaning |
|---|---|---|
| `MIN_CLEARANCE_M` | `0.5` | minimum allowed clearance from any surface |
| `MAX_MISSION_DURATION_S` | `900` | abort threshold |
| `TAKEOFF_HEIGHT_M` | `1.5` | hover height after takeoff, before traversal |
| `AISLE_TRAVERSAL_HEIGHT_M` | `1.0` | transit altitude inside an aisle when not capturing |
| `LINK_LOSS_TIMEOUT_S` | `5` | seconds of comms loss before return-to-home |
| `MIN_CAPTURE_RESOLUTION` | `4_000_000` (4 MP) | per-image pixel floor |
| `MIN_FOCUS_SCORE` | empirical | Laplacian variance floor |

### 10.4 Determinism

Path derivation is **pure**: same map + same tunables → identical waypoint
list, byte-for-byte. The planner does no random sampling, no time-of-day
input, no environmental input. This is what makes ISC-7 (path length
matches hand-computed reference) probe-able.

---

## 11. Reference fixture

A small realistic example lives at
`tests/fixtures/maps/reference_warehouse.yaml`:

- 12 m × 8 m floor
- 2 aisles (A1, A2) running north-south
- 4 racks per side, 4 levels per rack
- 1 support-column no-go zone
- Total capture positions: **2 aisles × 2 sides × 4 racks × 4 levels = 64**

This fixture is the spine of validation:

- ISC-1 (load), ISC-7 (path length), ISC-16 (capture count), ISC-24
  (coverage arithmetic), ISC-31 (zero collisions), ISC-37 (coverage
  threshold) all reference it.

---

## 12. Versioning

`schema_version` is the only knob for compatibility. Backwards-incompatible
changes bump the version; the loader's `SUPPORTED_VERSIONS` is the source
of truth. Old maps remain loadable as long as their version is in the set;
deprecated versions are removed only when no production map references
them.

Additive fields (new optional keys, e.g., per-rack `bays` in v1.1) do NOT
require a version bump as long as omitting them yields v1.0 behavior.

---

## 13. What's intentionally absent

The schema deliberately does **not** carry:

- Any inventory, SKU, or bin content data.
- Any sensor calibration data (lives with the drone, not the map).
- Any mission scheduling data (`when`, `who`, `which battery`).
- Any waypoint list (waypoints are derived; never authored).

Adding any of these is a schema-version change, not an additive edit.
