# Quality gates for the dronePrjs umbrella.
# Uses the venv at .venv/ (created by Phase 0, NS-0.1).

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
SIM_DIR := engine/sim_gazebo/docker

.PHONY: all test lint typecheck install clean help \
        sim-build sim-up sim-down sim-shell sim-logs sim-world

help:
	@echo "Quality gates:  install | test | lint | typecheck | all | clean"
	@echo "Tier-2 sim:     sim-world | sim-build | sim-up | sim-down | sim-shell | sim-logs"

install:
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest --cov --cov-fail-under=80

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy closedSpace engine

all: lint typecheck test

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -not -path './$(VENV)/*' -exec rm -rf {} +

# ---------------------------------------------------------------------
# Tier-2 sim (NS-3.1, NS-3.2): Gazebo Harmonic + PX4 SITL in Docker.
# The image is large (several GB) and the first build is slow (~15–30 min)
# — intentionally NOT wired into `make all`.

sim-world:
	$(PY) -m closedSpace.sim.world_builder \
	  closedSpace/tests/fixtures/maps/reference_warehouse.yaml \
	  engine/sim_gazebo/worlds/reference_warehouse.sdf

sim-build:
	cd $(SIM_DIR) && docker compose build

sim-up:
	cd $(SIM_DIR) && docker compose up -d

sim-down:
	cd $(SIM_DIR) && docker compose down

sim-shell:
	cd $(SIM_DIR) && docker compose exec sim bash

sim-logs:
	cd $(SIM_DIR) && docker compose logs -f
