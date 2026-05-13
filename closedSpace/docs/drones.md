# Drones for closedSpace — platforms, software, cost, accessories

> Survey of drone hardware, software stacks, costs, and accessories
> suitable for the closedSpace warehouse-inventory use case. Scoped to
> the constraints in `ISA.md`: GPS-denied indoor flight, ≤2.4 m aisles,
> 0.5 m clearance envelope, <50 ms control-loop latency, ≤15 min
> mission, Python-controllable from `closedSpace/`.
>
> Prices are USD, 2024-era list/street; verify current quotes before
> purchase. URLs intentionally omitted — vendor sites move; search the
> vendor name + product name to find current docs.

---

## How the project's constraints filter the drone choice

Before any platform survey, the ISA's constraints already narrow the
field. A drone is a **fit candidate for closedSpace** only if:

| ISA constraint | Hardware implication |
|---|---|
| GPS-denied (`SLAMProvider`, no `GPSProvider`) | Onboard VIO or full SLAM stack mandatory; consumer GPS-only drones are out |
| 2.4 m aisles, 0.5 m clearance | Diagonal drone width ≲ 50 cm including prop guards |
| `<50 ms` p99 control loop | Onboard compute, not cloud — cloud-in-the-loop adds 100–500 ms |
| Python integration via engine Protocols | SDK or open firmware (PX4/ArduPilot) — closed-loop systems with no dev access are blocked |
| 4 MP minimum capture, focus-quality gate | Dedicated capture camera (RGB ≥ 4 MP) separate from VIO sensors |
| ≤15 min mission, indoors | Small-to-medium LiPo (4S, 3500–5500 mAh) is sufficient |
| Operator-first (non-pilot staff) | Strong autonomy — failsafes, return-to-home, abort, prop guards |
| Capture-then-offload (no onboard recognition) | Modest compute is fine — Jetson Orin Nano class is plenty |

Net effect: the universe of viable platforms is small. Roughly four
shapes, covered below.

---

## Drone categories

### Category A — Vendor-as-service (the buy-the-outcome path)

You don't pick a drone; the vendor brings their drone, their software,
and their on-site staff. Closest to "drone-in-a-box" for warehouse
inventory.

| Vendor | Country | Notes |
|---|---|---|
| **Verity** | CH | Most established. Custom autonomous drones, deployed at DSV, IKEA, Maersk. Sells as a recurring service per-warehouse, not as a platform. |
| **Corvus Robotics** | US | Corvus One drone, autonomous fleet, US-focused. Service model. |
| **Doks Innovation** | DE | inventAIRy XL — quadcopter often paired with a mobile robot base. Service-leaning. |
| **Eyesee (Hardis Group)** | FR | Eyesee drone, primarily European deployments. |
| **PINC AIR** | US | RFID-based inventory drones (different sensing modality). |

**Cost shape:** opaque — typically per-warehouse / per-mission service
contracts in the high-five-figure to mid-six-figure annual range,
including onboarding survey, software, and ongoing flights.

**Fit for closedSpace:** **not a fit if you're building closedSpace
yourself** — these vendors *replace* the system we're spec'ing. Listed
here because (a) they prove the use case is real and commercially
viable, and (b) they may be the right answer for some pilot
warehouses if the goal is operations, not platform development.

---

### Category B — Purpose-built dev platforms (the build-with-good-bones path)

Drones designed from the ground up for autonomous indoor work, with
companion compute, depth sensing, and SDKs already wired up. Closest
to "100 m head start" for a custom build.

| Platform | Vendor | Approx cost (drone only) | Notes |
|---|---|---|---|
| **ModalAI Starling 2 / Starling 2 Max** | ModalAI (US) | ~$3.5k–6k | Built around VOXL 2 SoC (Snapdragon 865 + dedicated DSPs); PX4-flashed; onboard VIO, ToF, RGB; Linux companion compute integrated. The closest thing to "PX4 + Jetson + RealSense + Pixhawk in one box, pre-tuned." |
| **ModalAI Sentinel** | ModalAI | ~$5k–8k | Larger, longer endurance, payload bay for extra cameras. |
| **Holybro X500 V2 + companion** | Holybro (TW) | ~$1.5k frame + $0.5k–1k Pixhawk + $0.3k–1k companion = ~$2.5k–4k | Reference PX4 development airframe. Add Pixhawk 6X + Jetson Orin Nano + RealSense D455 yourself. More work, more flexibility. |
| **Skydio X10D** | Skydio (US) | ~$15k+ | Best-in-class VIO and obstacle avoidance. Skydio's enterprise SDK access has tightened post-2023 pivot; verify SDK terms before committing. Probably overspec'd for warehouse inventory. |

**Fit for closedSpace:** **Strong fit, especially ModalAI**. Starling-class
platforms align almost exactly with the ISA constraints and ship with
a software stack we can plug Python on top of via MAVLink + ROS 2.

---

### Category C — Custom builds (the maximum-control path)

Frame, flight controller, companion compute, sensors, props, batteries
— all chosen separately and integrated. Highest engineering cost, lowest
unit BOM cost, complete platform control.

Typical bill of materials for an indoor warehouse build:

| Component | Example | Approx cost |
|---|---|---|
| Frame (carbon, ~450 mm wheelbase, with prop guards) | Holybro X500 V2 / iFlight DC5 | $300–700 |
| Flight controller | Pixhawk 6X / Pixhawk 6C / Cube Orange+ | $300–600 |
| ESCs | Holybro Tekko32 (4-in-1) | $100–200 |
| Motors (4×) | T-Motor F60 / Sunnysky | $80–200 set |
| Propellers (low-energy, set) | Various — prefer "indoor safe" / 5-inch | $20–50 / spare set |
| Companion compute | Jetson Orin Nano dev kit / Orin NX | $250–1000 |
| Depth + IMU camera (VIO) | Intel RealSense D455 / D435i | $300–500 |
| RGB capture camera | Sony IMX477 module / GoPro Hero 12 / industrial USB | $150–600 |
| Battery (4S 5200 mAh LiPo) | Tattu / CNHL | $80–150 |
| GPS module | **omitted** — closedSpace constraint forbids `GPSProvider` | — |
| Telemetry radio | RFD900x or Holybro SiK | $100–300 |
| RC receiver + transmitter (manual override) | TBS Crossfire / ExpressLRS + RadioMaster | $200–400 |
| Indoor positioning aids | AprilTag prints (free), optional UWB anchors | $0–2000 |
| Charger / safe LiPo storage | iCharger / ToolkitRC + LiPo bag | $150–300 |
| **Per-drone BOM total** | | **~$2.5k–6k** |
| **First-build engineering effort** | | **~3–6 weeks for one full-time engineer** |

**Fit for closedSpace:** **viable for v1 but slower start than Category B**.
Recommended only if there's a strategic reason to own every layer
(differentiated sensor, atypical airframe, specific certification path).

---

### Category D — Research / micro platforms (the prove-the-software-first path)

Tiny drones suitable for software prototyping in a small lab, not for
real warehouse missions. Useful as the FIRST target before any
investment in Category B/C hardware — the engine `flight_control` and
`localization` Protocols can be wired up and tested against these.

| Platform | Vendor | Approx cost | Notes |
|---|---|---|---|
| **Crazyflie 2.1+** | Bitcraze (SE) | ~$230 (drone) + ~$500 (Lighthouse positioning) | Tiny (~92 mm motor-to-motor); excellent open-source ecosystem; Lighthouse base stations give absolute indoor positioning to ~1 mm. Payload too small for real capture cameras, but perfect for Phase-0/Phase-1 software bring-up. |
| **DJI Tello / Tello EDU / RoboMaster TT** | Ryze / DJI | ~$100–200 | Cheap, Python SDK exists, but very limited autonomy and SDK depth. Useful for the very first hello-world hover. |
| **Bitcraze Crazyswarm** | Bitcraze + research | — | Multi-Crazyflie coordination platform. Out of scope for v1 (single-drone). |

**Fit for closedSpace:** **excellent for Phase 0 and Phase 1**. Run the
mission planner against a Crazyflie + Lighthouse to validate
end-to-end flow before paying for a Starling-class drone.

---

## Software stacks

A drone's software splits roughly into four layers. Each layer is
chosen somewhat independently; some platforms bundle them.

### 1. Flight controller firmware (lowest, runs on the FC microcontroller)

| Stack | License | Best for | Notes |
|---|---|---|---|
| **PX4** | BSD | Autonomous research + commercial | MAVLink protocol; large community; pairs naturally with ROS 2 and Gazebo SITL. Default for Category B and most Category C builds. |
| **ArduPilot** | GPLv3 | Mature autonomous + manual | Slightly older roots; very battle-tested; MAVLink. License is GPL — important if you ever modify the firmware (most projects don't). |
| **Betaflight / iNav** | GPL | FPV / racing / not autonomous | Wrong tool — minimal autonomy support. Skip. |
| **DJI proprietary** | closed | DJI airframes | Access via DJI Mobile/Onboard/Payload/Edge SDKs; SDK terms have tightened over time. |
| **Skydio Autonomy** | closed | Skydio airframes | SDK access via Skydio's enterprise program. |

**Recommendation for closedSpace:** **PX4**. Default in Category B,
clean fit for Category C, well-supported by Gazebo simulator (Phase 3
of `next-steps.md`).

### 2. Companion-computer middleware (runs on the Linux SoC alongside the FC)

| Stack | License | Notes |
|---|---|---|
| **ROS 2** (Humble / Iron / Jazzy) | Apache 2.0 | De facto standard for autonomous robots; rich ecosystem (nav2, MoveIt, perception_pcl). Pairs with PX4 via `px4_ros_com` / `micrortps`. |
| **MAVROS** | LGPL | MAVLink ↔ ROS 1/2 bridge. Mature; many examples. |
| **PX4 ROS 2 user library** | BSD | Newer, native ROS 2 ↔ PX4 integration. |
| **Rust / direct MAVLink** | varies | For projects that want a thin stack — bypass ROS, talk MAVLink directly. Engine `flight_control` Protocol could wrap either. |

**Recommendation for closedSpace:** **ROS 2 + MAVROS** at first
(broadest examples, fastest bring-up), with the engine Protocol
abstracting it so we can swap to direct MAVLink later if ROS becomes a
liability.

### 3. SLAM / VIO (perception → pose)

| Stack | License | Hardware target | Notes |
|---|---|---|---|
| **VINS-Fusion / VINS-Mono** | GPLv3 | Stereo or mono + IMU | HKUST; well-tested; many drones run it. |
| **ORB-SLAM3** | GPLv3 | Stereo / RGB-D / mono + IMU | Salient-feature based; works in textured environments; struggles with featureless walls (R1 risk in `next-steps.md`). |
| **OpenVINS** | GPLv3 | Mono/stereo + IMU | UDel; lightweight EKF-based VIO; good for resource-constrained companion compute. |
| **RTAB-Map** | BSD | RGB-D | Loop-closure-strong; pairs with RealSense D-series. |
| **Kimera** | BSD | Stereo + IMU + semantic | MIT SPARK lab; multi-sensor; richer map. |
| **Bitcraze Lighthouse positioning** | BSD-ish | Crazyflie + 2× SteamVR base stations | Absolute positioning, not VIO; fits Category D phase. |
| **DJI / Skydio onboard VIO** | closed | Their drones | Excellent quality, no dev access at the algorithm level — you consume pose, you don't tune. |

**Risk reminder (R1 from `next-steps.md`):** featureless aisles can defeat
pure visual SLAM. Mitigate with **AprilTag fiducials** at aisle endpoints
and / or RGB-D + IMU fusion (D455 + ORB-SLAM3 RGB-D mode is a common
recipe). Indoor-positioning-anchor systems (UWB, Lighthouse) sidestep
the problem entirely if the warehouse can be instrumented.

**Recommendation for closedSpace:** **AprilTags + RealSense D455 +
VINS-Fusion** as the v1 baseline; reconsider after pilot feedback.

### 4. Simulator (for Phase 3 of `next-steps.md`)

Already covered in `next-steps.md` D2. Quick recap:

| Sim | Pairs with | Cost / license |
|---|---|---|
| **In-process kinematic Python sim** | PX4 (mocked) | We write it. Free. |
| **Gazebo Garden / Harmonic + PX4 SITL** | PX4 | Open source. |
| **Cosys-AirSim** | PX4 / ArduPilot | Open source (Unreal license complications for redistribution). |
| **NVIDIA Isaac Sim** | many | Free for individuals; license for commercial; GPU-heavy. |
| **jMAVSim** | PX4 | Open source; lightweight; not visually rich. |

### 5. Ground control station (for manual override + telemetry)

| GCS | Notes |
|---|---|
| **QGroundControl** | Cross-platform; the default for PX4. Can run on a tablet during flight. |
| **Mission Planner** | Windows-leaning; ArduPilot-focused. |
| **MAVProxy** | CLI; great for scripted mission tests. |
| **Custom dashboard** | Most production systems eventually build one — see `OperatorConsole` Feature in ISA. |

**Recommendation for closedSpace:** **QGroundControl** during
development for raw MAVLink visibility, with `OperatorConsole`
(`closedSpace.run` — Phase 5) as the production operator surface.

---

## Cost matrix by project phase

Tying drone choice back to the project phases in `next-steps.md`:

| Phase | Recommended hardware | One-time HW cost | Why |
|---|---|---|---|
| Phase 0–2 (foundations, planner, engine contracts) | None — pure software | $0 | Smoke runner + in-process kinematic sim is enough. |
| Phase 3 (simulator bring-up) | None for sim tier; optional Crazyflie + Lighthouse for early flight feel | $0–$750 | Crazyflie validates the engine Protocols against a real-but-tiny drone. |
| Phase 4–5 (capture, storage, report, console) | Crazyflie carries forward; or Starling 2 if budget allows | $0–$5k | Capture pipeline can be tested with a USB webcam first. |
| Phase 6 (quality gates) | None | $0 | CI work. |
| Phase 7 (MapBuilderFromWMS) | None | $0 | Mostly file-format work. |
| Phase 8 (pilot mission, real warehouse) | Production drone — Starling 2 / Sentinel **or** Category B/C build | $5k–$15k for one drone + accessories | First real-warehouse flight. |
| **Pre-pilot total HW** | | **$5k–$15k** | One drone + spares + ground station. |
| **Per-warehouse pilot operations** | | **$5k–$15k / warehouse** | Survey, integration, 1-week onsite, depending on warehouse size. |

For comparison: a Category-A vendor service (Verity, Corvus) typically
prices in the **$30k–$200k+ per-warehouse-per-year** range,
all-inclusive. The build-it path makes sense if you're targeting
deployments at scale or differentiating on platform; service makes
sense if the goal is operations at one or two sites and you don't want
the platform burden.

---

## Accessories

Independent of which drone class is chosen, the following are needed
or strongly recommended.

### Always required

| Item | Approx cost | Notes |
|---|---|---|
| Spare propellers (3–5 sets) | $30–250 | Indoor flying scuffs props; budget for replacements. |
| Spare LiPo batteries (3–5) | $250–750 | Mission durations (15 min) plus charge-cycle time means 3+ batteries to keep flying. |
| Smart charger + LiPo-safe storage bag | $150–300 | Safety. Non-negotiable. |
| Carrying / charging case | $100–500 | Protects sensors and frame in transit; usually has cutouts for batteries and tools. |
| Calibration kit (level surface, magnetic-clean area, IMU rotation jig) | $50–200 | Required by pre-flight checklist (ISC-28). |
| RC transmitter for manual override | $200–500 | Required as a safety fallback even on autonomous platforms. |
| Tablet or laptop for ground control | $300–2000 | Runs QGroundControl + `closedSpace.run`. |

### Required for indoor SLAM in featureless warehouses (R1 mitigation)

| Item | Approx cost | Notes |
|---|---|---|
| AprilTag fiducial prints (laminated, mountable) | $0–$200 | Print on cardstock; laminate; mount at aisle endpoints + corners + takeoff pad. Free if you have a printer; the cost is in the mounting hardware. |
| Optional: UWB anchor system (Pozyx, Decawave Qorvo MDEK1001) | $1k–$3k | 4–8 anchors per warehouse; gives absolute positioning that doesn't depend on visual texture. |
| Optional: Bitcraze Lighthouse base stations (research / Crazyflie tier only) | $600 | Two base stations cover ~5 m × 5 m well. |

### For the capture pipeline (UC-5)

| Item | Approx cost | Notes |
|---|---|---|
| RGB capture camera (≥4 MP, fixed focus or autofocus, USB or MIPI) | $150–600 | Separate from VIO sensors. Industrial USB cameras (e.g., FLIR Blackfly S) for repeatability; GoPro for ease; Sony IMX-class for quality. |
| LED illumination ring or panel (if warehouse lighting is poor) | $50–300 | Mount on drone; warehouse lighting often inadequate at top-shelf heights. |
| Onboard storage (microSD ≥128 GB) | $20–80 | Fast write rate matters; UHS-II preferable. |
| Lens cleaning kit | $20 | Dust accumulates fast in active warehouses. |

### For operations & maintenance

| Item | Approx cost | Notes |
|---|---|---|
| Spare ESCs, motors, frame parts | $200–500 | Indoor crashes happen during bring-up. |
| Soldering kit + heatshrink + connectors | $100–300 | LiPo connector replacement is routine. |
| IMU / compass calibration tools | $50–200 | Pre-flight requirement. |
| Mission-data offload drive (external SSD ≥1 TB) | $80–200 | Mission images sync here post-flight before backend upload. |

### Optional but valuable

| Item | Approx cost | Notes |
|---|---|---|
| Spare drone (entire second airframe) | full BOM | A grounded drone is the most expensive thing in your stack. Pilot warehouses usually demand a backup. |
| Test space — 5×5 m clear room with ceiling ≥3 m | — | Cheaper than a real warehouse for the first hundred test flights. |
| Drone net / catch system for crash testing | $200–800 | If using outside a closed test space. |
| LiPo fire-resistant storage container | $100–300 | Insurance / safety requirement at many sites. |

---

## Recommended stack for closedSpace v1

Pulling it together — a concrete proposal that matches the ISA
constraints, the `next-steps.md` phasing, and the budget shape above.

### Phase 0–2 (today through Engine contracts)

- **No drone purchase yet.** Smoke runner + in-process kinematic sim
  in `engine/sim/` carries all software work to this point.

### Phase 3 (simulator bring-up)

- **In-process kinematic sim** (we write — NS-2.5).
- **Gazebo Garden + PX4 SITL** for integration tier (NS-3.1).
- Optional cheap reality check: **Crazyflie 2.1+ + Lighthouse base
  stations** (~$750 total) for a small lab fly-through that exercises
  the engine Protocols against real flight dynamics. Skip if budget
  is tight; the kinematic sim catches most of the value.

### Phase 4–5 (capture, console)

- **USB webcam** for the first capture pipeline test (any 1080p USB
  camera, $30).
- Continue Crazyflie or graduate to Starling 2 once Phase 5 is close.

### Phase 8 (pilot)

- **Drone:** ModalAI Starling 2 Max (~$5–6k). Pre-flashed PX4, VOXL2
  companion, RealSense onboard, ToF for clearance — closest
  out-of-box match to the ISA constraints.
- **Capture camera:** add a higher-resolution module if Starling's
  native camera misses the 4 MP / focus-quality bar; otherwise use
  what's onboard. ($0–600.)
- **Fiducials:** AprilTags at aisle endpoints, takeoff pad, and
  warehouse corners. (~$50.)
- **GCS:** QGroundControl on a ruggedized tablet ($500).
- **Ops:** 3 spare batteries, charger, carry case, RC override,
  spare props. ($1–1.5k.)
- **Pilot warehouse readiness:** half-day site survey, AprilTag
  install, WiFi check, takeoff-pad designation, operator training.
  (~$3–5k operations cost depending on partner.)

**Total Phase 8 hardware bring-up:** **~$8k–$12k for one drone, one
spare battery set, accessories, and a tablet**, plus per-warehouse
operations.

This is the cheapest credible path from current state to first real
mission in a real warehouse without locking us into a specific vendor's
service model.

---

## Decision points — vendor questions to answer before purchase

Before any drone purchase, these need answers (record in ISA
`## Decisions`):

1. **Build vs buy-as-service?** Are we building closedSpace as a
   product, or operating it for one customer? The latter may favor a
   Category-A vendor partnership over Category B/C.
2. **Single platform, or platform-agnostic?** The engine
   `flight_control` Protocol gives us platform abstraction; do we
   commit to one platform for v1 or design for two from day one?
3. **Skydio enterprise SDK access** — if Skydio X10D is interesting,
   confirm the SDK terms support the use case we need before
   investing.
4. **DJI restrictions** — DJI airframes have geofencing and SDK
   restrictions that vary by region; confirm none of these block
   indoor warehouse autonomous flight.
5. **Regulatory** — even indoor flight has insurance and operator
   certification implications; confirm with the pilot warehouse
   partner what they require.
6. **Connectivity** — will the warehouse provide reliable Wi-Fi where
   the drone needs it, or do we need an onboard cellular fallback?

---

## Where this connects back to the rest of the project

- `ISA.md` Constraints — every drone choice must pass the constraint
  filter at the top of this doc.
- `docs/use-cases.md` UC-1 / UC-5 / UC-6 / UC-7 — drone capabilities
  drive these flows.
- `docs/next-steps.md` Phase 3 D1/D2/D3 — the open decisions that
  gate hardware choice (sim vs hardware, simulator, flight stack).
- `engine/` Protocols — the drone-platform abstraction layer; whatever
  drone is picked, it implements `engine.localization.SLAMProvider`
  and friends.

---

## Update cadence

This doc goes stale fast. Hardware prices change, vendors get acquired,
SDK terms shift. Re-check at:

- Phase 3 start — pre-purchase reality check.
- Pre-pilot — confirm the chosen platform is still the right call.
- Annually post-launch — drone hardware iterates yearly.
