.PHONY: setup demo test eval eval-regression lint format

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/pre-commit install

demo:
	$(PYTHON) -m agent_runtime.cli demo

test:
	$(PYTHON) -m pytest

eval:
	$(PYTHON) -m agent_runtime.evalkit run

# Expected to exit non-zero. This is the "CI would block this PR" demo.
eval-regression:
	$(PYTHON) -m agent_runtime.evalkit regression

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy
	$(PYTHON) -m agent_runtime.secretscan

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .
