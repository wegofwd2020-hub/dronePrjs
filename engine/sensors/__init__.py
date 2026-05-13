"""engine.sensors — camera, IMU, depth, fiducial sensor abstractions.

v1 ships the :class:`Camera` Protocol and a stdlib-only
:func:`laplacian_focus_score` helper. IMU / depth / fiducial Protocols
will be added when consumers appear (Phase 4 capture / report).

Focus score (Laplacian variance)
--------------------------------

The standard cheap blur detector: convolve grayscale pixels with the
4-neighbour Laplacian kernel ``[[0,1,0],[1,-4,1],[0,1,0]]`` and take the
variance of the result. Sharp images have heavy tails (variance high);
blurry images smooth out (variance low). v1 deliberately avoids a
numpy / opencv dependency — the implementation is ~20 lines and works
fine for the v1 synthetic frames the sim emits and the small thumbnails
the mission report uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from engine.types import Pose


@dataclass(frozen=True, slots=True)
class Frame:
    """One captured image plus the metadata sidecar.

    ``pixels`` is raw single-channel grayscale data row-major; the
    accompanying ``width`` / ``height`` give the buffer's shape. Real
    cameras would emit RGB / Bayer; the v1 sim emits grayscale because
    the focus-score helper is grayscale-only. Multi-channel comes
    when a real camera lands.
    """

    pixels: bytes
    width: int
    height: int
    pose: Pose
    focus_score: float


@runtime_checkable
class Camera(Protocol):
    """Single-frame capture surface.

    Implementations may stream internally (rolling shutter, autoexposure);
    ``capture`` returns one finalized :class:`Frame` per call. The host
    is responsible for the dwell time between command and capture.
    """

    def start(self) -> None:
        """Power-on / open the device. Idempotent."""
        ...

    def stop(self) -> None:
        """Release the device. Safe to call twice."""
        ...

    def capture(self, pose: Pose) -> Frame:
        """Grab one frame and stamp it with the host-provided pose.

        Pose is passed in (not read from a SLAMProvider) because the
        host's flight-control loop is the source of truth for "what
        pose was this image taken at" — and decoupling the camera
        from the localization stack keeps the Protocols composable.
        """
        ...


def laplacian_focus_score(
    pixels: Sequence[int], width: int, height: int
) -> float:
    """Variance of the 4-neighbour Laplacian over an 8-bit grayscale buffer.

    Args:
        pixels: Row-major grayscale values, length ``width * height``.
        width: Pixels per row.
        height: Number of rows.

    Returns:
        Variance of the Laplacian-filtered interior pixels (excludes the
        1-pixel border). Higher = sharper. Zero for uniform images.

    Raises:
        ValueError: If ``len(pixels) != width * height`` or dimensions
            are too small to have any interior pixels.
    """
    expected = width * height
    if len(pixels) != expected:
        raise ValueError(
            f"pixel buffer length {len(pixels)} != width*height {expected}"
        )
    if width < 3 or height < 3:
        raise ValueError(
            f"need at least 3x3 to compute Laplacian; got {width}x{height}"
        )

    laplacian: list[int] = []
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            c = pixels[row + x]
            n = pixels[row - width + x]
            s = pixels[row + width + x]
            e = pixels[row + x + 1]
            w = pixels[row + x - 1]
            laplacian.append(n + s + e + w - 4 * c)

    n = len(laplacian)
    mean = sum(laplacian) / n
    return sum((v - mean) ** 2 for v in laplacian) / n


__all__ = ["Camera", "Frame", "laplacian_focus_score"]
