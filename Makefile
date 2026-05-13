# Quality gates for the dronePrjs umbrella.
# Uses the venv at .venv/ (created by Phase 0, NS-0.1).

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: all test lint typecheck install clean help

help:
	@echo "Targets: install | test | lint | typecheck | all | clean"

install:
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy closedSpace engine

all: lint typecheck test

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -not -path './$(VENV)/*' -exec rm -rf {} +
