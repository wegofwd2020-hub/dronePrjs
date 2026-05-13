"""Tests for :class:`closedSpace.storage.LocalSink`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from closedSpace.storage import LocalSink, StorageError


def test_write_persists_image_and_sidecar(tmp_path: Path) -> None:
    sink = LocalSink(tmp_path / "mission-123")
    art = sink.write(
        relative_path="wh-1/A1/A1-W1/0/20260513T100000-000000Z.jpg",
        image_bytes=b"\x01\x02\x03",
        sidecar={"rack_id": "A1-W1", "level_index": 0},
    )
    assert art.image_path.read_bytes() == b"\x01\x02\x03"
    sidecar = json.loads(art.sidecar_path.read_text())
    assert sidecar["rack_id"] == "A1-W1"
    assert art.relative_path.endswith(".jpg")


def test_write_creates_nested_dirs(tmp_path: Path) -> None:
    sink = LocalSink(tmp_path / "m")
    art = sink.write(
        relative_path="x/y/z/file.bin",
        image_bytes=b"",
        sidecar={},
    )
    assert art.image_path.parent.is_dir()
    assert art.image_path.is_file()


def test_write_is_atomic_via_rename(tmp_path: Path) -> None:
    """A .partial file MUST NOT remain visible after a successful write."""
    sink = LocalSink(tmp_path / "m")
    sink.write(relative_path="a.jpg", image_bytes=b"x", sidecar={})
    leftovers = list((tmp_path / "m").rglob("*.partial"))
    assert leftovers == []


def test_rejects_absolute_or_empty_relative_path(tmp_path: Path) -> None:
    sink = LocalSink(tmp_path / "m")
    with pytest.raises(StorageError, match="relative_path"):
        sink.write(relative_path="/abs.jpg", image_bytes=b"", sidecar={})
    with pytest.raises(StorageError, match="relative_path"):
        sink.write(relative_path="", image_bytes=b"", sidecar={})
