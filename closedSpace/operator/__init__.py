"""closedSpace.operator — ground-station-facing mission control.

Sits between the planner (pure) + capture/storage/report (durable) and
the human running the mission. Public surface:

* :class:`PreflightChecklist` + :class:`PreflightResult` — pre-arm gate.
* :class:`MissionRunner` — drives plan → sim → capture → storage →
  report with abort polling and 1 Hz progress.
* :class:`AbortSignal` — programmatic abort source the CLI binds to
  stdin (or the test binds to a method call).

The CLI shim itself is :mod:`closedSpace.run`; this package is its
import target and is reusable by anything that needs a programmatic
mission entry point (integration tests, future API server, etc.).
"""
from __future__ import annotations

from closedSpace.operator.preflight import (
    PreflightCheck,
    PreflightChecklist,
    PreflightOutcome,
    PreflightResult,
)
from closedSpace.operator.runner import (
    AbortSignal,
    MissionRunner,
    MissionRunResult,
)

__all__ = [
    "AbortSignal",
    "MissionRunResult",
    "MissionRunner",
    "PreflightCheck",
    "PreflightChecklist",
    "PreflightOutcome",
    "PreflightResult",
]
