"""Post-flight sync coordinator + remote-sink Protocol.

Sync runs after the mission has landed. For each persisted artifact:

* If the :class:`RemoteSink` returns cleanly, the artifact's local copy
  is **left in place** (we never delete after upload — operators want
  the local archive too).
* If the sink raises, we write a ``<image>.sync-pending`` marker
  alongside the local copy. The next sync attempt picks up only the
  artifacts whose marker still exists (out of scope for v1).

ISC-22 and ISC-32 are the contract this module enforces: sync failure
must never destroy local data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from closedSpace.storage.local import StoredArtifact

#: Filename suffix written next to artifacts whose upload failed. The
#: marker file holds the failure reason as plain text.
SYNC_PENDING_SUFFIX = ".sync-pending"


class SyncFailure(Exception):
    """Raised by a :class:`RemoteSink` to signal a non-fatal upload failure.

    Non-fatal means: keep the local copy, mark it pending, continue with
    the next artifact. Fatal infrastructure errors should propagate as
    plain ``OSError`` / ``RuntimeError`` and abort sync entirely.
    """


@runtime_checkable
class RemoteSink(Protocol):
    """The external upload surface — S3, HTTP, NFS, whatever.

    Implementations MUST be idempotent: the same artifact uploaded
    twice produces the same remote state. v1 has no resume / partial-
    upload semantics, so each ``upload`` is one all-or-nothing call.
    """

    def upload(self, artifact: StoredArtifact) -> None:
        """Ship one artifact. Raise :class:`SyncFailure` on retryable error."""
        ...


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Aggregate outcome of a sync pass."""

    uploaded: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]  # (relative_path, reason)

    @property
    def all_succeeded(self) -> bool:
        return not self.failed


def sync_to_remote(
    artifacts: Sequence[StoredArtifact], remote: RemoteSink
) -> SyncResult:
    """Upload every artifact; mark failures with a ``.sync-pending`` file.

    Local artifacts are never modified or deleted by this function —
    that's the ISC-32 invariant. Successful uploads only clear the
    sync-pending marker if one was left from a prior run.
    """
    uploaded: list[str] = []
    failed: list[tuple[str, str]] = []

    for art in artifacts:
        marker = _marker_path(art.image_path)
        try:
            remote.upload(art)
        except SyncFailure as e:
            marker.write_text(str(e), encoding="utf-8")
            failed.append((art.relative_path, str(e)))
            continue

        uploaded.append(art.relative_path)
        if marker.exists():
            marker.unlink()

    return SyncResult(uploaded=tuple(uploaded), failed=tuple(failed))


def _marker_path(image_path: Path) -> Path:
    return image_path.with_suffix(image_path.suffix + SYNC_PENDING_SUFFIX)
