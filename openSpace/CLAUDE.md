# openSpace

Outdoor / unrestricted-airspace drone operations. GPS-available,
long-range, higher altitudes. Wind and weather are first-class concerns.

## Domain rules
- Position estimation primary source is GPS, fused with IMU.
- Geofencing and airspace classes (e.g., FAA Class B/C/D) must be
  validated before any mission start.
- Mission durations can exceed 60 min — battery, telemetry buffering,
  and reconnect logic must reflect that.

## Sub-project commands
- `python -m openSpace.run --mission <plan.yaml>`

## Engine usage
- Use `engine.localization.GPSProvider` with IMU fusion.
- (any other domain-specific engine wiring notes)
