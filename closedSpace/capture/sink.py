"""Per-capture gate + sidecar composer + storage handoff."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Union

from closedSpace.mission import Waypoint
from closedSpace.storage import LocalSink, StorageError, StoredArtifact
from engine.sensors import Frame


class MissReason(Enum):
    """Why a single capture was not recorded.

    Kept as a closed enum so the report's machine-readable ``reason``
    field has a finite vocabulary downstream tooling can switch on.
    """

    LOW_RESOLUTION = "low_resolution"
    LOW_FOCUS = "low_focus"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class CaptureRecorded:
    """A capture passed the gates and is durably written."""

    waypoint: Waypoint
    artifact: StoredArtifact
    focus_score: float
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CaptureMissed:
    """A capture failed a gate or could not be persisted."""

    waypoint: Waypoint
    reason: MissReason
    detail: str


CaptureOutcome = Union[CaptureRecorded, CaptureMissed]


class CaptureSink:
    """Stateful per-mission consumer of captured frames.

    One :class:`CaptureSink` lives for the duration of one mission.
    Construct it with the mission's identifiers and gate thresholds;
    call :meth:`consume` once per capture waypoint with the
    :class:`Frame` the camera emitted.
    """

    def __init__(
        self,
        *,
        warehouse_id: str,
        mission_id: str,
        storage: LocalSink,
        min_capture_resolution_px: int,
        min_focus_score: float,
        image_extension: str = "jpg",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._warehouse_id = warehouse_id
        self._mission_id = mission_id
        self._storage = storage
        self._min_resolution = min_capture_resolution_px
        self._min_focus = min_focus_score
        self._ext = image_extension.lstrip(".")
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def consume(self, waypoint: Waypoint, frame: Frame) -> CaptureOutcome:
        """Run the gates and persist on pass; return the outcome either way."""
        if not waypoint.capture:
            raise ValueError(
                f"consume() called on non-capture waypoint {waypoint.kind!r}"
            )

        resolution_px = frame.width * frame.height
        if resolution_px < self._min_resolution:
            return CaptureMissed(
                waypoint=waypoint,
                reason=MissReason.LOW_RESOLUTION,
                detail=(
                    f"{frame.width}x{frame.height} = {resolution_px} px "
                    f"< {self._min_resolution} px"
                ),
            )

        if frame.focus_score < self._min_focus:
            return CaptureMissed(
                waypoint=waypoint,
                reason=MissReason.LOW_FOCUS,
                detail=(
                    f"focus_score {frame.focus_score:.2f} < {self._min_focus:.2f}"
                ),
            )

        now = self._clock()
        relative_path = self._compose_filename(waypoint, now)
        sidecar = self._compose_sidecar(waypoint, frame, now, relative_path)

        try:
            artifact = self._storage.write(
                relative_path=relative_path,
                image_bytes=frame.pixels,
                sidecar=sidecar,
            )
        except StorageError as e:
            return CaptureMissed(
                waypoint=waypoint,
                reason=MissReason.STORAGE_ERROR,
                detail=str(e),
            )

        return CaptureRecorded(
            waypoint=waypoint,
            artifact=artifact,
            focus_score=frame.focus_score,
            width=frame.width,
            height=frame.height,
        )

    def _compose_filename(self, wp: Waypoint, ts: datetime) -> str:
        """ISC-18 pattern: warehouse_id/aisle_id/rack_id/level/{ts}.{ext}.

        ``:`` and ``.`` from the ISO timestamp are flattened to ``-`` so
        the path is safe on every filesystem v1 cares about.
        """
        aisle_id = str(wp.metadata["aisle_id"])
        rack_id = str(wp.metadata["rack_id"])
        level_index = int(wp.metadata["level_index"])
        stamp = ts.strftime("%Y%m%dT%H%M%S-%f") + "Z"
        return (
            f"{self._warehouse_id}/{aisle_id}/{rack_id}/{level_index}/"
            f"{stamp}.{self._ext}"
        )

    def _compose_sidecar(
        self,
        wp: Waypoint,
        frame: Frame,
        ts: datetime,
        relative_path: str,
    ) -> dict[str, Any]:
        """ISC-17 sidecar shape — kept terse on purpose; report sums it up."""
        return {
            "mission_id": self._mission_id,
            "warehouse_id": self._warehouse_id,
            "aisle_id": str(wp.metadata["aisle_id"]),
            "rack_id": str(wp.metadata["rack_id"]),
            "level_index": int(wp.metadata["level_index"]),
            "pose": {
                "x": frame.pose.x,
                "y": frame.pose.y,
                "z": frame.pose.z,
                "yaw_deg": frame.pose.yaw_deg,
            },
            "timestamp_utc": ts.isoformat(),
            "image_uri": relative_path,
            "focus_score": frame.focus_score,
            "resolution": {"width": frame.width, "height": frame.height},
        }
