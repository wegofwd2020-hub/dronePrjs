"""closedSpace.storage — local-first capture writes + post-flight sync.

Two responsibilities live here:

* :class:`LocalSink` — write image bytes + JSON sidecar atomically to a
  per-mission directory, fsync before the next waypoint is attempted
  (ISC-21). The capture pipeline holds exactly one of these.
* :class:`RemoteSink` Protocol + :func:`sync_to_remote` — after the
  mission ends, iterate local artifacts and ship them to whatever
  external backend the deployment uses (S3, NAS, HTTP API). On failure,
  local copies are retained and a ``{path}.sync-pending`` marker is
  written. **Sync failure must never delete local data** (ISC-22, ISC-32).

The :class:`RemoteSink` is a Protocol, not a concrete class, because the
choice between S3 / NFS / HTTP is operator-environment-specific and not
worth committing to in v1.
"""
from __future__ import annotations

from closedSpace.storage.local import (
    LocalSink,
    StorageError,
    StoredArtifact,
)
from closedSpace.storage.sync import (
    RemoteSink,
    SyncFailure,
    SyncResult,
    sync_to_remote,
)

__all__ = [
    "LocalSink",
    "RemoteSink",
    "StorageError",
    "StoredArtifact",
    "SyncFailure",
    "SyncResult",
    "sync_to_remote",
]
