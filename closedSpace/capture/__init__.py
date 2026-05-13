"""closedSpace.capture — per-waypoint image gate + sidecar writer.

The :class:`CaptureSink` is what the mission runner hands each captured
:class:`~engine.sensors.Frame` to, along with the capture waypoint it
came from. The sink:

* Checks the resolution gate (``width * height >= min_capture_resolution_px``,
  ISC-19) and focus gate (``focus_score >= min_focus_score``, ISC-20). A
  failed gate produces a :class:`CaptureMissed` outcome — the report
  records it; the runner does not block.
* On a pass, composes the §ISC-18 filename pattern and the §ISC-17
  sidecar, hands the bytes + JSON to :class:`~closedSpace.storage.LocalSink`,
  and returns a :class:`CaptureRecorded`.

Gate thresholds and the timestamp clock are injected, not hard-coded,
so tests can dial sim-realistic values without rebuilding the mission
config every time.
"""
from __future__ import annotations

from closedSpace.capture.sink import (
    CaptureMissed,
    CaptureOutcome,
    CaptureRecorded,
    CaptureSink,
    MissReason,
)

__all__ = [
    "CaptureMissed",
    "CaptureOutcome",
    "CaptureRecorded",
    "CaptureSink",
    "MissReason",
]
