"""Tests for the post-flight sync coordinator.

The ISC contract is: a sync failure MUST NOT delete or modify the local
copy of an artifact. We verify both the happy and unhappy paths against
in-memory fake :class:`RemoteSink` implementations.
"""
from __future__ import annotations

from pathlib import Path

from closedSpace.storage import (
    LocalSink,
    StoredArtifact,
    SyncFailure,
    sync_to_remote,
)


class _OKSink:
    def __init__(self) -> None:
        self.uploaded: list[str] = []

    def upload(self, artifact: StoredArtifact) -> None:
        self.uploaded.append(artifact.relative_path)


class _AlwaysFailsSink:
    def upload(self, artifact: StoredArtifact) -> None:
        raise SyncFailure("network unreachable")


def _persist_one(local: LocalSink, name: str = "wh/A/R/0/a.jpg") -> StoredArtifact:
    return local.write(relative_path=name, image_bytes=b"img", sidecar={"k": 1})


def test_successful_sync_leaves_local_in_place(tmp_path: Path) -> None:
    local = LocalSink(tmp_path / "m")
    art = _persist_one(local)
    remote = _OKSink()

    result = sync_to_remote([art], remote)

    assert result.all_succeeded
    assert remote.uploaded == [art.relative_path]
    assert art.image_path.is_file()
    assert art.sidecar_path.is_file()


def test_sync_failure_preserves_local_and_writes_marker(tmp_path: Path) -> None:
    """ISC-22 + ISC-32: failure path keeps local data and marks it pending."""
    local = LocalSink(tmp_path / "m")
    art = _persist_one(local)
    remote = _AlwaysFailsSink()

    result = sync_to_remote([art], remote)

    assert not result.all_succeeded
    assert result.failed == ((art.relative_path, "network unreachable"),)
    # Local copy and sidecar still present
    assert art.image_path.is_file()
    assert art.sidecar_path.is_file()
    # Marker exists with the failure reason as plain text
    marker = art.image_path.with_suffix(art.image_path.suffix + ".sync-pending")
    assert marker.is_file()
    assert "network unreachable" in marker.read_text()


def test_successful_resync_clears_existing_marker(tmp_path: Path) -> None:
    """A pre-existing .sync-pending marker is removed when upload finally succeeds."""
    local = LocalSink(tmp_path / "m")
    art = _persist_one(local)
    marker = art.image_path.with_suffix(art.image_path.suffix + ".sync-pending")
    marker.write_text("prior failure", encoding="utf-8")

    sync_to_remote([art], _OKSink())

    assert not marker.exists()
