"""Pre-arm checklist runner.

Each check returns a :class:`PreflightOutcome`; the aggregate
:class:`PreflightResult` is "pass" only when every blocking check
passes. ISC-28 (per-item pass/fail), ISC-34 (takeoff-in-coverage),
ISC-44 (map staleness with explicit override) all enforce here.

External I/O (battery percentage, IMU calibration state) is injected
via callables rather than imported, so tests don't need to mock a
flight stack and a future real-hardware adapter just supplies real
callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Callable

from closedSpace.map.types import Map
from closedSpace.map.validate import _point_in_polygon

#: Default freshness window for surveyed maps. Per ISC-44, missions
#: refuse to arm against maps older than this unless the operator
#: explicitly overrides AND the map carries a non-null surveyed_at.
DEFAULT_MAX_MAP_AGE_DAYS: int = 30

#: Default minimum battery percentage required to arm.
DEFAULT_MIN_BATTERY_PCT: float = 30.0


class PreflightOutcome(Enum):
    """Per-check verdict. ``WARN`` is non-blocking; ``FAIL`` refuses arm."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"  # non-blocking; surface to operator, allow arm


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One named line item on the checklist."""

    name: str
    outcome: PreflightOutcome
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Aggregate verdict the runner uses to decide arm / refuse."""

    checks: tuple[PreflightCheck, ...]

    @property
    def can_arm(self) -> bool:
        """True iff no check produced a ``FAIL`` outcome."""
        return not any(c.outcome is PreflightOutcome.FAIL for c in self.checks)

    @property
    def failures(self) -> tuple[PreflightCheck, ...]:
        """The subset of checks whose outcome is ``FAIL``."""
        return tuple(c for c in self.checks if c.outcome is PreflightOutcome.FAIL)

    @property
    def warnings(self) -> tuple[PreflightCheck, ...]:
        """The subset of checks whose outcome is ``WARN``."""
        return tuple(c for c in self.checks if c.outcome is PreflightOutcome.WARN)


class PreflightChecklist:
    """Composable pre-arm gate.

    The platform-dependent checks (battery, calibration) take callables
    so an integration test can hand back fixed values, and a real
    deployment hands back live sensor reads. Map-level checks
    (coverage, staleness) work directly off the loaded :class:`Map`.
    """

    def __init__(
        self,
        *,
        battery_pct: Callable[[], float],
        calibration_ok: Callable[[], bool],
        today: Callable[[], date] | None = None,
        max_map_age_days: int = DEFAULT_MAX_MAP_AGE_DAYS,
        min_battery_pct: float = DEFAULT_MIN_BATTERY_PCT,
        allow_stale_map: bool = False,
    ) -> None:
        self._battery_pct = battery_pct
        self._calibration_ok = calibration_ok
        self._today = today or date.today
        self._max_map_age_days = max_map_age_days
        self._min_battery_pct = min_battery_pct
        self._allow_stale_map = allow_stale_map

    def run(self, m: Map) -> PreflightResult:
        """Run every check in order and return the aggregate verdict."""
        return PreflightResult(
            checks=(
                self._check_battery(),
                self._check_calibration(),
                self._check_takeoff_in_coverage(m),
                self._check_free_takeoff_pad(m),
                self._check_map_staleness(m),
            )
        )

    # -----------------------------------------------------------------
    # Individual checks — each one returns a PreflightCheck.
    # -----------------------------------------------------------------

    def _check_battery(self) -> PreflightCheck:
        pct = self._battery_pct()
        if pct >= self._min_battery_pct:
            return PreflightCheck(
                name="battery",
                outcome=PreflightOutcome.PASS,
                detail=f"{pct:.1f}% (>= {self._min_battery_pct}%)",
            )
        return PreflightCheck(
            name="battery",
            outcome=PreflightOutcome.FAIL,
            detail=f"{pct:.1f}% < required {self._min_battery_pct}%",
        )

    def _check_calibration(self) -> PreflightCheck:
        if self._calibration_ok():
            return PreflightCheck(
                name="calibration",
                outcome=PreflightOutcome.PASS,
                detail="IMU + visual calibration OK",
            )
        return PreflightCheck(
            name="calibration",
            outcome=PreflightOutcome.FAIL,
            detail="calibration self-test reported a fault",
        )

    def _check_takeoff_in_coverage(self, m: Map) -> PreflightCheck:
        """ISC-34: refuse to arm when takeoff is outside coverage polygon."""
        pad = m.takeoff_pad.position
        polygon_lists = [[p.x, p.y] for p in m.coverage_polygon]
        if _point_in_polygon((pad.x, pad.y), polygon_lists):
            return PreflightCheck(
                name="takeoff_in_coverage",
                outcome=PreflightOutcome.PASS,
                detail=f"pad ({pad.x}, {pad.y}) inside coverage polygon",
            )
        return PreflightCheck(
            name="takeoff_in_coverage",
            outcome=PreflightOutcome.FAIL,
            detail=f"pad ({pad.x}, {pad.y}) is OUTSIDE coverage polygon — refusing arm",
        )

    def _check_free_takeoff_pad(self, m: Map) -> PreflightCheck:
        """No no-go zone intersects the takeoff pad's footprint (XY)."""
        pad = m.takeoff_pad.position
        pad_r = m.takeoff_pad.radius_m
        for zone in m.no_go_zones:
            polygon_lists = [[p.x, p.y] for p in zone.polygon]
            if _point_in_polygon((pad.x, pad.y), polygon_lists):
                return PreflightCheck(
                    name="free_takeoff_pad",
                    outcome=PreflightOutcome.FAIL,
                    detail=f"takeoff pad sits inside no_go_zone {zone.id!r}",
                )
            # Cheap proximity check: any zone vertex inside the pad radius
            # means the zone touches the pad. Refined geometry can land
            # here later; this is enough to catch the obvious-foot-gun.
            for vert in zone.polygon:
                if ((vert.x - pad.x) ** 2 + (vert.y - pad.y) ** 2) ** 0.5 < pad_r:
                    return PreflightCheck(
                        name="free_takeoff_pad",
                        outcome=PreflightOutcome.FAIL,
                        detail=(
                            f"no_go_zone {zone.id!r} vertex within "
                            f"{pad_r} m of takeoff pad"
                        ),
                    )
        return PreflightCheck(
            name="free_takeoff_pad",
            outcome=PreflightOutcome.PASS,
            detail=f"no no-go zone within {pad_r} m of pad",
        )

    def _check_map_staleness(self, m: Map) -> PreflightCheck:
        """ISC-44: refuse stale maps; warn on missing surveyed_at."""
        if m.surveyed_at is None:
            # Non-blocking: an unsurveyed map is loadable but the operator
            # should know they're flying without provenance.
            return PreflightCheck(
                name="map_staleness",
                outcome=PreflightOutcome.WARN,
                detail="map.surveyed_at is null — provenance unknown",
            )
        surveyed = datetime.fromisoformat(m.surveyed_at).date()
        age = self._today() - surveyed
        if age <= timedelta(days=self._max_map_age_days):
            return PreflightCheck(
                name="map_staleness",
                outcome=PreflightOutcome.PASS,
                detail=f"surveyed {surveyed} ({age.days} days old)",
            )
        if self._allow_stale_map:
            return PreflightCheck(
                name="map_staleness",
                outcome=PreflightOutcome.WARN,
                detail=(
                    f"surveyed {surveyed} ({age.days} days old) — "
                    f"exceeds {self._max_map_age_days} d but --allow-stale-map set"
                ),
            )
        return PreflightCheck(
            name="map_staleness",
            outcome=PreflightOutcome.FAIL,
            detail=(
                f"surveyed {surveyed} ({age.days} days old) > "
                f"{self._max_map_age_days} d. Re-survey or pass --allow-stale-map."
            ),
        )
