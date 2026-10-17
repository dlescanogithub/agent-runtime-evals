.PHONY: setup demo test eval eval-regression eval-live lint format

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/pre-commit install

demo:
	$(PYTHON) -m agent_runtime.cli demo

# Prints how to record docs/demo.gif and runs the demo. Does not write a GIF.
demo-gif:
	$(PYTHON) scripts/record_demo_gif.py

test:
	$(PYTHON) -m pytest --cov-fail-under=80

eval:
	$(PYTHON) -m agent_runtime.evalkit run

# Expected to exit non-zero. This is the "CI would block this PR" demo.
eval-regression:
	$(PYTHON) -m agent_runtime.evalkit regression

# Hosted models only. Refuses to start unless LIVE_MODE=1 and the spend cap
# are set. Writes cassettes under var/live-evals, never evals/cassettes.
# CI does not run this.
eval-live:
	$(PYTHON) -m agent_runtime.evalkit live

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy
	$(PYTHON) -m agent_runtime.secretscan

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .
