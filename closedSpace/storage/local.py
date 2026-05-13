"""Local-first capture writer.

The :class:`LocalSink` is the destination for in-flight image writes.
Each :meth:`write` call:

1. Materializes the full directory path beneath the mission root.
2. Writes image bytes to a ``.partial`` file, fsyncs, then renames to
   the final path — so an interrupted write never leaves a half-image
   visible to a concurrent reader or post-flight sync (ISC-21, ISC-32).
3. Writes the JSON sidecar with the same atomic-rename pattern.
4. Returns a :class:`StoredArtifact` the report builder records.

A single mission owns a single :class:`LocalSink` rooted at
``<base>/<mission_id>/``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StorageError(Exception):
    """Local write failed for a reason the caller cannot easily retry."""


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """One persisted (image, sidecar) pair, in absolute paths.

    ``relative_path`` is the per-mission-root-relative path the operator
    sees; the report uses it as the ``image_uri`` field (ISC-17).
    """

    image_path: Path
    sidecar_path: Path
    relative_path: str


class LocalSink:
    """Atomic per-waypoint writer rooted at one mission directory.

    The mission root is created on construction. Subdirectories are
    created lazily by each :meth:`write`. Method is **synchronous and
    durable**: control returns only after both files have been fsynced
    to disk, so the mission runner can advance to the next waypoint
    knowing the previous capture is safe (ISC-21).
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StorageError(f"cannot create mission root {self._root}: {e}") from e

    @property
    def root(self) -> Path:
        """Absolute path to the per-mission directory this sink writes under."""
        return self._root

    def write(
        self,
        *,
        relative_path: str,
        image_bytes: bytes,
        sidecar: dict[str, Any],
    ) -> StoredArtifact:
        """Persist one capture. Returns the resulting :class:`StoredArtifact`.

        ``relative_path`` is the on-disk path beneath the mission root
        per §ISC-18, e.g. ``ref-wh-01/A1/A1-W1/0/2026...jpg``. The
        sidecar JSON shares the basename with ``.json`` appended.
        """
        if not relative_path or relative_path.startswith("/"):
            raise StorageError(
                f"relative_path must be a relative non-empty string: {relative_path!r}"
            )

        image_path = self._root / relative_path
        sidecar_path = image_path.with_suffix(image_path.suffix + ".json")
        try:
            image_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(image_path, image_bytes)
            _atomic_write_bytes(
                sidecar_path,
                json.dumps(sidecar, indent=2, sort_keys=True).encode("utf-8"),
            )
        except OSError as e:
            raise StorageError(
                f"failed to write capture {relative_path!r}: {e}"
            ) from e

        return StoredArtifact(
            image_path=image_path,
            sidecar_path=sidecar_path,
            relative_path=relative_path,
        )


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write + fsync + rename. Guarantees the target appears atomically."""
    tmp = target.with_suffix(target.suffix + ".partial")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
