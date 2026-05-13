"""engine.localization — position estimation providers.

Phase 2 introduces a ``PositionProvider`` Protocol with two concrete
implementations:

* ``SLAMProvider`` — visual-inertial odometry; required for closedSpace.
* ``GPSProvider`` — GPS + IMU fusion; required for openSpace.

closedSpace MUST NOT import ``GPSProvider``; openSpace MUST NOT import
``SLAMProvider`` as primary. See each sub-project's CLAUDE.md.
"""
