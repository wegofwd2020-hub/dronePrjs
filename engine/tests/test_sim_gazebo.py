"""Scaffold-level tests for engine.sim_gazebo (tier-2 sim package).

NS-3.1 only ships the package skeleton + Docker setup; concrete Protocol
implementations land in NS-3.3 (SLAMProvider) and NS-3.4 (Camera). These
tests pin the scaffold so a missing __init__ or a broken docker compose
file is caught in CI, and so the package has a test mirror from day one.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_PKG_NAME = "engine.sim_gazebo"
_DOCKER_DIR = Path(__file__).resolve().parents[1] / "sim_gazebo" / "docker"


def test_package_imports() -> None:
    module = importlib.import_module(_PKG_NAME)
    assert module.__doc__ and "tier-2" in module.__doc__.lower(), (
        "engine.sim_gazebo must carry a module docstring identifying it as "
        "tier-2 sim; tier identity is load-bearing for test selection."
    )


@pytest.mark.parametrize("filename", ["Dockerfile", "docker-compose.yml", ".dockerignore"])
def test_docker_artifact_present(filename: str) -> None:
    path = _DOCKER_DIR / filename
    assert path.is_file(), (
        f"NS-3.1 scaffold expected {path.relative_to(_DOCKER_DIR.parents[2])}; "
        f"`make sim-build` will fail without it."
    )


def test_worlds_dir_present() -> None:
    worlds = _DOCKER_DIR.parent / "worlds"
    assert worlds.is_dir(), (
        "NS-3.2 will populate engine/sim_gazebo/worlds/ with SDF files "
        "generated from closedSpace map fixtures; the mount in "
        "docker-compose.yml assumes this directory already exists."
    )
