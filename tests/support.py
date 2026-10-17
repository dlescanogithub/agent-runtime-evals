"""Shared helpers for driving a run the way the eval harness does."""

from __future__ import annotations

from agent_runtime.runner import AgentRunner
from agent_runtime.types import RunOutcome


def approve_until_done(runner: AgentRunner, outcome: RunOutcome) -> RunOutcome:
    for _ in range(8):
        if outcome.status != "waiting_review" or not outcome.pending:
            return outcome
        for pending in outcome.pending:
            runner.decide(outcome.run_id, pending.step_id, "approve")
        outcome = runner.resume(outcome.run_id)
    return outcome
