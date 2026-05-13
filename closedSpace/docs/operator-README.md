# closedSpace — Operator Walkthrough

> Cold start → mission report in ≤ 15 minutes. ISC-42's verification
> target is "a warehouse staffer who has never flown a drone can
> complete a reference mission end-to-end using only this README."
> If you read something here that needs a glossary entry, file it.

This walkthrough assumes the drone has been pre-paired with the
ground-station laptop and the warehouse YAML map has already been
exported from the WMS. Both of those happen once per warehouse, not
per mission.

---

## 1. Before you start

You need three things on the laptop:

1. **A Python environment.** If `python -m closedSpace.run --help`
   prints usage, you're set. If not, the dev team has a one-page
   "set up the laptop" runbook — get it from them.
2. **A warehouse map file.** A YAML file with the same `warehouse_id`
   as the warehouse you're standing in. Filename convention is
   `<warehouse-id>.yaml`.
3. **The drone, charged, on its takeoff pad.** Battery ≥ 30 %.

Take 30 seconds to look around the takeoff pad: nothing within an
arm's length, no people in the aisles you plan to fly.

---

## 2. Launch the mission console

Open a terminal and run:

```bash
python -m closedSpace.run --map ~/maps/<warehouse-id>.yaml
```

You'll see a **plan summary** like this:

```
============================================================
  Mission plan — warehouse: ref-wh-01
  Map surveyed_at: 2026-04-15
------------------------------------------------------------
  Aisles:                2
  Capture waypoints:     64
  Total waypoints:       70
  Path length:           118.03 m
  Est. duration:         310 s (5.2 min)
============================================================
```

Read the summary out loud. If the warehouse id, aisle count, or
estimated duration look wrong, hit **Ctrl-C** and go find the dev
team. Don't proceed if anything looks off.

---

## 3. The preflight gate

Right after the summary, you'll see five lines starting with
`[OK]`, `[WARN]`, or `[FAIL]`:

```
Preflight:
  [OK]    battery               87.3% (>= 30.0%)
  [OK]    calibration           IMU + visual calibration OK
  [OK]    takeoff_in_coverage   pad (1.0, 1.0) inside coverage polygon
  [OK]    free_takeoff_pad      no no-go zone within 0.5 m of pad
  [OK]    map_staleness         surveyed 2026-04-15 (28 days old)
```

**Any `[FAIL]` and the mission won't arm.** The CLI exits with
code 2; the line above the prompt tells you which check failed.
Common causes:

| Failure | What to do |
|---|---|
| `battery` low | Swap in the charged battery and re-run. |
| `calibration` | The drone's self-test failed — call the dev team. |
| `takeoff_in_coverage` | You've got the wrong map. Confirm the `warehouse_id` matches the building you're in. |
| `free_takeoff_pad` | The takeoff pad placement conflicts with a no-go zone in the map. Don't fly. |
| `map_staleness` | Map is older than 30 days. Either request a fresh survey OR — if you've checked with operations — re-run with `--allow-stale-map`. |

`[WARN]` is informational. The map_staleness warning under
`--allow-stale-map` means: "the map is old, you've acknowledged it,
proceed at your own risk."

---

## 4. The confirmation prompt

If everything passes, the CLI asks:

```
Proceed with mission? [yes/no]
```

**Type `yes` and press Enter.** Nothing else counts — `y`, `YES`,
`yes please` are not accepted. This is deliberate: arming requires
unambiguous consent.

If you typed anything else, the CLI exits with code 3 and the drone
never armed.

---

## 5. During the mission

The drone will:

1. Take off to ~1.5 m hover height.
2. Fly to the entry of the first aisle.
3. Traverse the aisle, pausing at every shelf level to capture one
   image. You'll hear the rotors steady as it holds, then resume.
4. Transition to the next aisle (boustrophedon — opposite end so
   transit is short).
5. Land back on the takeoff pad.

Estimated duration is printed in the plan summary. **Stay within
arm's reach of the laptop the whole time** — the abort key works
only there.

### Abort

Press **Ctrl-C** in the terminal. The drone will:

- If airborne → land at its current XY position immediately.
- If on the ground / armed → disarm.

The CLI then exits with code 4 and produces a partial mission
report.

---

## 6. After landing

The CLI prints something like:

```
Mission complete. Report: missions/m-a3b1c2d4/mission_report.json
  captured: 64 / 64
  coverage: 100.00%
```

The mission directory contains:

- One JPG per capture, in
  `<warehouse_id>/<aisle_id>/<rack_id>/<level>/<timestamp>.jpg`
- A `.json` sidecar next to each JPG with pose + metadata.
- `mission_report.json` — the post-flight summary.
- `telemetry.jsonl` — the 1 Hz event log (developer artifact).

Send the entire `missions/<mission-id>/` folder to the inventory
team. They take it from there.

If `coverage` is below 100 %, the report's `missed_waypoints`
section lists which `(aisle, rack, level)` tuples the drone could
not capture and why. Common reasons:

- `low_resolution` — camera produced a sub-spec frame. Hardware
  problem; call the dev team.
- `low_focus` — too blurry. Often a single bad capture, occasionally
  a calibration drift.
- `storage_error` — disk full or write fault. Free space and re-fly.

---

## 7. What you didn't have to know

You didn't have to know:

- The map's geometry (the planner derives all 64 capture poses).
- The exact aisle direction (boustrophedon is automatic).
- How focus scoring works (the gate runs itself).
- How to wire up SLAM or calibrate the IMU (the preflight runs the
  self-test).

That's by design. If a future revision of this CLI asks for any of
the above, push back — it's a regression.
