PY ?= python

.PHONY: install check lint format typecheck test run

install:
	$(PY) -m pip install -r requirements-dev.txt

# The single gate command. Its exit code is the verdict for humans, agents and CI alike.
check: lint typecheck test

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest

run:
	$(PY) -m uvicorn app.main:app --reload
