"""engine.flight_control — flight-stack-agnostic command surface.

Phase 2 introduces a ``FlightController`` Protocol so PX4, ArduPilot,
DJI/Skydio SDKs, and the in-process simulator all sit behind one
interface. Choice of flight stack is open decision D3 in
``closedSpace/docs/next-steps.md``.
"""
