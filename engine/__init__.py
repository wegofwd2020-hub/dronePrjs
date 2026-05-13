"""engine — shared core for closedSpace and openSpace drone applications.

The engine is the contract between the two domain sub-projects. Anything
domain-specific belongs in ``closedSpace/`` or ``openSpace/`` — not here.

Sub-packages:

* :mod:`engine.localization` — position estimation providers.
* :mod:`engine.flight_control` — flight-stack-agnostic command surface.
* :mod:`engine.telemetry` — in-flight telemetry plumbing.
* :mod:`engine.sensors` — camera, IMU, depth, fiducials.

Phase 2 (per ``closedSpace/docs/next-steps.md``) fills these with Protocols
and stub implementations. Today they exist so domain code can ``import``
the names without breaking.
"""
