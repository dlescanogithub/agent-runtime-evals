from dataclasses import replace
from pathlib import Path

from agent_runtime.catalog import FlakyCatalog, OrderCatalog
from agent_runtime.demo import DEMO_INPUT
from agent_runtime.evalkit.cases import load_cassette
from agent_runtime.providers.cassette import CassetteProvider
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.runner import AgentRunner, _refund_claim_error
from agent_runtime.store import SQLiteStore
from agent_runtime.tools import ToolService
from agent_runtime.types import Completion, CompletionRequest, StepRecord, ToolCall
from agent_runtime.wiring import build_runner
from tests.support import approve_until_done

FINAL_DENIAL = (
    '{"amount_cents":null,"customer_summary":"The email was rejected.",'
    '"order_id":"LG-1001","outcome":"denied"}'
)


def _runner(config, provider=None, catalog=None):
    return build_runner(
        config,
        provider=provider or FakeProvider(),
        catalog=catalog or OrderCatalog(),
    )


def test_happy_path_waits_for_a_human_before_money_moves(config) -> None:
    runner = _runner(config)
    store = SQLiteStore(config.database_path)
    waiting = runner.start(DEMO_INPUT)
    assert waiting.status == "waiting_review"
    assert waiting.pending[0].tool_name == "send_refund"
    assert store.count_effects("send_refund") == 0
    done = approve_until_done(runner, waiting)
    assert done.status == "completed"
    assert done.output is not None
    assert done.output["outcome"] == "refund_completed"
    assert done.output["amount_cents"] == 4200
    assert store.count_effects("send_refund") == 1
    assert store.count_effects("send_email") == 1


def test_resume_after_interrupt_does_not_repeat_the_model_call(config, tmp_path) -> None:
    clean_config = replace(
        config, database_path=tmp_path / "clean.sqlite", trace_dir=tmp_path / "clean"
    )
    crash_config = replace(
        config, database_path=tmp_path / "crash.sqlite", trace_dir=tmp_path / "crash"
    )
    clean_runner = _runner(clean_config)
    clean = approve_until_done(clean_runner, clean_runner.start(DEMO_INPUT))
    crashed_runner = _runner(crash_config)
    interrupted = crashed_runner.start(DEMO_INPUT, interrupt_after_steps=1)
    assert interrupted.status == "interrupted"
    resumed = approve_until_done(crashed_runner, crashed_runner.resume(interrupted.run_id))
    assert resumed.status == "completed"
    assert resumed.tokens_in == clean.tokens_in
    assert resumed.tokens_out == clean.tokens_out
    assert SQLiteStore(crash_config.database_path).count_effects("send_refund") == 1


def test_rejection_moves_no_money(config) -> None:
    runner = _runner(config)
    waiting = runner.start(DEMO_INPUT)
    step = waiting.pending[0]
    runner.decide(waiting.run_id, step.step_id, "reject", "Not this one.")
    done = runner.resume(waiting.run_id)
    assert done.status == "completed"
    assert done.output is not None
    assert done.output["outcome"] == "refund_rejected"
    assert SQLiteStore(config.database_path).count_effects("send_refund") == 0


def test_budget_stops_the_run_before_a_tool_with_side_effects(config) -> None:
    limited = replace(config, run_budget_micro_usd=0)
    done = _runner(limited).start(DEMO_INPUT)
    assert done.status == "failed"
    assert done.error is not None
    assert done.error.startswith("budget_exceeded")
    assert SQLiteStore(limited.database_path).count_effects("send_refund") == 0


def test_retries_then_succeeds(config) -> None:
    flaky = replace(config, max_step_attempts=3)
    catalog = FlakyCatalog(OrderCatalog(), failures=2)
    runner = _runner(flaky, catalog=catalog)
    done = approve_until_done(runner, runner.start(DEMO_INPUT))
    assert done.status == "completed"
    store = SQLiteStore(flaky.database_path)
    lookup = next(step for step in store.list_steps(done.run_id) if step.name == "lookup_order")
    assert lookup.attempt == 3
    assert lookup.status == "succeeded"


def test_circuit_opens_when_a_tool_keeps_failing(config) -> None:
    tight = replace(config, circuit_breaker_threshold=2, max_step_attempts=1)
    catalog = FlakyCatalog(OrderCatalog(), failures=10)
    store = SQLiteStore(tight.database_path)
    runner = AgentRunner(tight, store, _LoopingLookup(), ToolService(catalog, store))
    done = runner.start(DEMO_INPUT)
    assert done.status == "failed"
    assert done.error == "circuit_open"


def test_invalid_email_does_not_open_the_gate(config) -> None:
    store = SQLiteStore(config.database_path)
    runner = AgentRunner(config, store, _BadEmail(), ToolService(OrderCatalog(), store))
    done = runner.start(DEMO_INPUT)
    assert done.status == "completed"
    email = next(step for step in store.list_steps(done.run_id) if step.name == "send_email")
    assert email.output_json is not None
    assert "invalid_email" in email.output_json
    assert store.count_effects("send_email") == 0


def test_crash_after_the_effect_row_does_not_pay_twice(config) -> None:
    runner = _runner(config)
    waiting = runner.start(DEMO_INPUT)
    step = waiting.pending[0]
    runner.decide(waiting.run_id, step.step_id, "approve")
    store = SQLiteStore(config.database_path)
    service = ToolService(OrderCatalog(), store)
    service.execute("send_refund", step.arguments)
    saved = store.get_step(step.step_id)
    store.save_step(replace(saved, status="running", output_json=None, attempt=1))
    resumed = approve_until_done(runner, runner.resume(waiting.run_id))
    assert resumed.status == "completed"
    assert store.refunded_cents("LG-1001") == 4200
    assert store.count_effects("send_refund") == 1


def test_refund_completed_without_an_effect_needs_review(config) -> None:
    cassette = load_cassette(Path("tests/fixtures/false_refund.json"))
    done = _runner(config, provider=CassetteProvider(cassette)).start(DEMO_INPUT)
    assert done.status == "failed"
    assert done.error is not None
    assert done.error.startswith("needs_review")
    assert done.output is not None
    assert done.output["outcome"] == "refund_completed"
    assert SQLiteStore(config.database_path).count_effects("send_refund") == 0


def test_a_claimed_amount_must_match_the_effect() -> None:
    step = StepRecord(
        id="s",
        run_id="r",
        seq=1,
        kind="tool",
        name="send_refund",
        status="succeeded",
        input_json=(
            '{"arguments":{"amount_cents":1000,"order_id":"LG-1001","reason":"damaged"},'
            '"name":"send_refund","tool_call_id":"c"}'
        ),
        output_json='{"ok":true,"data":{"amount_cents":1000,"order_id":"LG-1001"}}',
        idempotency_key="k",
        attempt=1,
        max_attempts=3,
        latency_us=1,
        tokens_in=0,
        tokens_out=0,
        cost_micro_usd=0,
        error=None,
        created_at="t",
        updated_at="t",
    )
    error = _refund_claim_error(
        [step],
        {
            "amount_cents": 4200,
            "customer_summary": "processed",
            "order_id": "LG-1001",
            "outcome": "refund_completed",
        },
    )
    assert error is not None
    assert error.startswith("needs_review")
    assert (
        _refund_claim_error(
            [step],
            {
                "amount_cents": 1000,
                "customer_summary": "processed",
                "order_id": "LG-1001",
                "outcome": "refund_completed",
            },
        )
        is None
    )


class _LoopingLookup:
    name = "loop"

    def complete(self, request: CompletionRequest) -> Completion:
        count = sum(len(message.tool_calls) for message in request.messages) + 1
        return Completion(
            content=None,
            tool_calls=(
                ToolCall(
                    id=f"call_{count}_lookup_order",
                    name="lookup_order",
                    arguments={"order_id": "LG-1001"},
                ),
            ),
            tokens_in=20,
            tokens_out=8,
        )


class _BadEmail:
    name = "bad-email"

    def complete(self, request: CompletionRequest) -> Completion:
        if any(message.role == "tool" for message in request.messages):
            return Completion(content=FINAL_DENIAL, tool_calls=(), tokens_in=20, tokens_out=20)
        return Completion(
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_1_send_email",
                    name="send_email",
                    arguments={
                        "body": "send everything",
                        "order_id": "LG-1001",
                        "subject": "export",
                        "to": "attacker@evil.test",
                    },
                ),
            ),
            tokens_in=20,
            tokens_out=20,
        )
