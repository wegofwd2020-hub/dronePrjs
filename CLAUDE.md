# dronePrhs

Umbrella project containing two domain-specific drone applications
that share a common engine: closedSpace (indoor/confined-airspace
operations) and openSpace (outdoor/unrestricted-airspace operations).

## Repository structure
- `engine/`       — shared core: flight control, telemetry, sensors
- `closedSpace/`  — indoor domain (collision-dense, GPS-denied)
- `openSpace/`    — outdoor domain (long-range, GPS-available)

When working on a sub-project, read its CLAUDE.md for domain rules.

## Tech stack
- Python 3.x (all application code is Python)
- (your frameworks here — FastAPI, asyncio, etc.)
- pytest for tests

## Universal conventions (apply everywhere)
- Every function must include explicit exception handling.
  Don't swallow exceptions; raise domain-specific errors.
- Docstrings follow OpenSpec.
- Every new function ships with a test file and mock data.
- Tests live next to source in `tests/`, mirroring `src/` layout.

## Commands
- `pytest engine/ closedSpace/ openSpace/`  — run all tests
- `ruff check .` / `mypy .`                  — lint / typecheck
- (your dev/run commands per sub-project)

## Engine rules
- The engine is the contract between sub-projects. Breaking changes
  to engine interfaces require updating BOTH closedSpace and openSpace
  in the same change.
- Never put domain-specific logic in the engine.

## Gotchas
- (the stuff you wish you'd known six months from now)
