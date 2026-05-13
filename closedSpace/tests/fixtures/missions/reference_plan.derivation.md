# Reference plan — hand-derived path length

Locks in ISC-7 (±5%) and ISC-8 (≤ 900 s) for `reference_warehouse.yaml`
at `MissionConfig` defaults.

## Inputs

- **Takeoff pad:** `(1.0, 1.0, 0.0)`
- **Aisle A1 centerline:** `(3.0, 1.5) → (3.0, 6.5)`, north-bound, `width_m = 2.4`
- **Aisle A2 centerline:** `(8.0, 1.5) → (8.0, 6.5)`, north-bound, `width_m = 2.4`
- **Racks per side per aisle:** 4 racks at `position_along ∈ {0.7, 1.9, 3.1, 4.3}`,
  `face_offset_m = 0.6` → capture stand-off `= 2.4/2 − 0.6 = 0.6 m` from centerline.
- **Levels per rack:** `z ∈ {0.5, 1.5, 2.5, 3.5}`
- **Config:** `TAKEOFF_HEIGHT_M = 1.5`, `AISLE_TRAVERSAL_HEIGHT_M = 1.0`,
  `speed = 1.0 m/s`, `capture_dwell = 3.0 s`.

Capture (x, y) positions:

| aisle | side  | x   | y for pos_along ∈ {0.7, 1.9, 3.1, 4.3}        |
|-------|-------|-----|-----------------------------------------------|
| A1    | west  | 2.4 | 2.2, 3.4, 4.6, 5.8                            |
| A1    | east  | 3.6 | 2.2, 3.4, 4.6, 5.8                            |
| A2    | west  | 7.4 | reversed: 5.8, 4.6, 3.4, 2.2 (entry-at-end)   |
| A2    | east  | 8.6 | reversed: 5.8, 4.6, 3.4, 2.2                  |

## Segment arithmetic

### Within a single rack (4 levels, ascending z)

Drone moves z 0.5 → 1.5 → 2.5 → 3.5 at fixed (x, y). **Per-rack capture
segments = 3.0 m.**

### Between consecutive racks on same side

Same x, dy = ±1.2 (rack spacing), dz = 3.0 (from z=3.5 of previous rack's
top level to z=0.5 of next rack's bottom level).

`sqrt(1.2² + 3.0²) = sqrt(10.44) ≈ 3.23110`

### Side-swap within an aisle (last west rack → first east rack)

Same aisle, dx = 1.2 (west→east offset), dy = −3.6 (y reset 5.8 → 2.2),
dz = −3.0.

`sqrt(1.2² + 3.6² + 3.0²) = sqrt(23.4) ≈ 4.83735`

### Per-aisle subtotal (excluding transit-in/out approaches)

`west: 4 × 3.0 + 3 × 3.23110 = 12.0 + 9.69330 = 21.69330`
`+ side-swap: 4.83735`
`+ east: 21.69330`
`= 48.22394`

### Transit-in approach (transit-in → first capture)

A1: `(3.0, 1.5, 1.0) → (2.4, 2.2, 0.5)` → dx=−0.6, dy=0.7, dz=−0.5.
`sqrt(0.36 + 0.49 + 0.25) = sqrt(1.10) ≈ 1.04881`

A2: `(8.0, 6.5, 1.0) → (7.4, 5.8, 0.5)` → identical distances.
**Symmetric: ≈ 1.04881.**

### Transit-out departure (last capture → transit-out)

A1: `(3.6, 5.8, 3.5) → (3.0, 6.5, 1.0)` → dx=−0.6, dy=0.7, dz=−2.5.
`sqrt(0.36 + 0.49 + 6.25) = sqrt(7.10) ≈ 2.66458`

A2: `(8.6, 2.2, 3.5) → (8.0, 1.5, 1.0)` → identical distances.

### Per-aisle total (transit-in → all captures → transit-out)

`1.04881 + 48.22394 + 2.66458 ≈ 51.93734 m`. Same for both aisles by
symmetry.

### Takeoff → A1 transit-in

`(1.0, 1.0, 1.5) → (3.0, 1.5, 1.0)` → dx=2, dy=0.5, dz=−0.5.
`sqrt(4 + 0.25 + 0.25) = sqrt(4.5) ≈ 2.12132`

### A1 transit-out → A2 transit-in

`(3.0, 6.5, 1.0) → (8.0, 6.5, 1.0)` → dx=5, dy=0, dz=0. **= 5.00000**

### A2 transit-out → landing

`(8.0, 1.5, 1.0) → (1.0, 1.0, 1.5)` → dx=−7, dy=−0.5, dz=0.5.
`sqrt(49 + 0.25 + 0.25) = sqrt(49.5) ≈ 7.03562`

## Total

```
2.12132    takeoff → A1 transit-in
51.93734   A1 (transit-in → captures → transit-out)
5.00000    A1 transit-out → A2 transit-in
51.93734   A2 (transit-in → captures → transit-out)
7.03562    A2 transit-out → landing
─────────
118.03162  m
```

## Duration

Captures: 64 × 3.0 s dwell = 192.0 s.
Travel: 118.03162 / 1.0 = 118.03162 s.
**Total ≈ 310.03 s** — well under the 900 s `MAX_MISSION_DURATION_S` cap.

## Waypoint count

`1 takeoff + 2 × (1 transit-in + 32 captures + 1 transit-out) + 1 landing = 70`
