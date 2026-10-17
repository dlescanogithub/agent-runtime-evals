"""One synthetic refund, with a crash and two human approvals.

The story is fixed so a demo on another machine spends the same tokens.
Latency is not part of the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_runtime.config import Config
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.store import SQLiteStore
from agent_runtime.wiring import build_runner

DEMO_INPUT: dict[str, object] = {
    "customer_message": "The lamp arrived cracked. Please refund the order.",
    "intent": "refund",
    "order_id": "LG-1001",
    "reason": "damaged",
    "requested_amount_cents": 4200,
}


@dataclass(frozen=True)
class DemoSummary:
    run_id: str
    final_status: str
    steps: int
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int
    refund_effects: int
    email_effects: int
    saw_interrupt: bool
    saw_waiting_review: bool
    amount_cents: int | None
    lines: tuple[str, ...]


def demo_config(base_dir: Path) -> Config:
    return Config(
        llm_provider="fake",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        openai_timeout_s=30,
        database_path=base_dir / "runtime.sqlite",
        trace_dir=base_dir / "traces",
        evals_dir=Path("evals"),
        check_threshold=0.8,
        run_budget_micro_usd=100_000,
        max_step_attempts=3,
        circuit_breaker_threshold=3,
        max_agent_steps=8,
        retry_backoff_ms=0,
        log_level="INFO",
        api_host="127.0.0.1",
        api_port=8080,
        api_token=None,
    )


def run_demo(base_dir: Path, config: Config | None = None) -> DemoSummary:
    if config is None:
        config = demo_config(base_dir)
    # The ledger remembers refunds. Wipe the demo folder so the command
    # shows the happy path every time instead of "already refunded".
    _reset_demo_files(config)
    runner = build_runner(config, provider=FakeProvider())
    lines: list[str] = [
        "Lumen Desk demo. Synthetic order, fake model, no API key.",
        "Case: LG-1001 damaged lamp, 4200 cents.",
    ]
    outcome = runner.start(DEMO_INPUT, interrupt_after_steps=1)
    saw_interrupt = outcome.status == "interrupted"
    lines.append(
        f"1. Stopped after the first model step. status={outcome.status} run={outcome.run_id}"
    )
    outcome = runner.resume(outcome.run_id)
    saw_review = outcome.status == "waiting_review"
    pending = ", ".join(item.tool_name for item in outcome.pending) or "none"
    lines.append(f"2. Resumed until the human gate. status={outcome.status} pending={pending}")
    step_number = 3
    while outcome.status == "waiting_review":
        if not outcome.pending:
            break
        step = outcome.pending[0]
        amount = step.arguments.get("amount_cents")
        lines.append(f"{step_number}. Approving {step.tool_name} amount_cents={amount}.")
        step_number += 1
        runner.decide(outcome.run_id, step.step_id, "approve")
        outcome = runner.resume(outcome.run_id)
    amount_cents = None
    if outcome.output is not None:
        raw_amount = outcome.output.get("amount_cents")
        if isinstance(raw_amount, int) and not isinstance(raw_amount, bool):
            amount_cents = raw_amount
    store = SQLiteStore(config.database_path)
    refund_effects = store.count_effects("send_refund")
    email_effects = store.count_effects("send_email")
    steps = len(store.list_steps(outcome.run_id))
    lines.append(
        f"{step_number}. Finished. status={outcome.status} outcome="
        f"{None if outcome.output is None else outcome.output.get('outcome')} "
        f"amount_cents={amount_cents}"
    )
    lines.append(
        f"{step_number + 1}. tokens_in={outcome.tokens_in} tokens_out={outcome.tokens_out} "
        f"cost_micro_usd={outcome.spent_micro_usd} steps={steps} "
        f"refund_effects={refund_effects} email_effects={email_effects}"
    )
    lines.append(f"{step_number + 2}. Trace directory: {config.trace_dir}")
    return DemoSummary(
        run_id=outcome.run_id,
        final_status=outcome.status,
        steps=steps,
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
        cost_micro_usd=outcome.spent_micro_usd,
        refund_effects=refund_effects,
        email_effects=email_effects,
        saw_interrupt=saw_interrupt,
        saw_waiting_review=saw_review,
        amount_cents=amount_cents,
        lines=tuple(lines),
    )


def _reset_demo_files(config: Config) -> None:
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{config.database_path}{suffix}")
        if path.exists():
            path.unlink()
    if config.trace_dir.exists():
        for trace in config.trace_dir.glob("*.jsonl"):
            trace.unlink()
