"""engine.sim_gazebo — tier-2 simulator: Gazebo Harmonic + PX4 SITL.

Companion to :mod:`engine.sim` (tier-1, in-process kinematic). Both
tiers implement the same engine Protocols
(:class:`engine.flight_control.FlightController`,
:class:`engine.localization.SLAMProvider`,
:class:`engine.sensors.Camera`,
:class:`engine.telemetry.TelemetryBus`); the difference is fidelity.

* **Tier 1 — `engine.sim`** drives unit + smoke tests. Zero install,
  deterministic, fast. Default for CI and developer inner loop.
* **Tier 2 — `engine.sim_gazebo`** (this module) drives integration
  tests that need realistic sensor returns: RGB-D for capture, IMU
  + visual features for SLAM-divergence probes (ISC-12 loss-of-
  tracking, ISC-13 latency, ISC-14 clearance), MAVLink for the
  flight stack.

Suitability gate:

* Use tier 1 for anything pose- or state-machine-level. It is
  several orders of magnitude faster and runs in any CI worker.
* Use tier 2 only when the test result depends on a sensor model
  the in-process sim cannot reproduce — image content, SLAM drift,
  PX4 flight-controller behavior, MAVLink semantics.

Status: scaffold only (NS-3.1). Concrete Protocol implementations
land in NS-3.3 (SLAMProvider) and NS-3.4 (Camera); end-to-end
integration test lands in NS-3.5. The Docker image and `make sim-*`
targets are runnable today; see ``docker/Dockerfile`` for the build
context.
"""
from __future__ import annotations
