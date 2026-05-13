# closedSpace

Indoor / confined-airspace drone operations. GPS-denied, high obstacle
density, low-altitude flight. Latency tolerance is tight (<50ms).

## Domain rules
- All position estimation goes through SLAM / visual-inertial odometry.
  Never trust GPS in this codebase — it isn't there.
- Default safety envelope: 0.5m clearance from any detected surface.
- Mission durations are short (<15 min); battery models reflect that.

## Sub-project commands
- `python -m closedSpace.run --map <map.yaml>` — run a mission

## Engine usage
- Use `engine.localization.SLAMProvider`, not `GPSProvider`.
- (any other domain-specific engine wiring notes)
