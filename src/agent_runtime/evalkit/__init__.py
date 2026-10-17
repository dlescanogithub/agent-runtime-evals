"""Eval gate. Deterministic checks always block. The checklist is code, not a model."""

from agent_runtime.evalkit.suite import run_regression, run_suite

__all__ = ["run_regression", "run_suite"]
