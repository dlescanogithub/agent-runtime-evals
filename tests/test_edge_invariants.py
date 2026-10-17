"""Four edge cases accept a safe path that is not the stub's tool list."""

import json
import sqlite3
from pathlib import Path

from agent_runtime.config import Config
from agent_runtime.evalkit.cases import load_cases
from agent_runtime.evalkit.suite import _run_case, run_suite
from agent_runtime.providers.cassette import CassetteProvider
from agent_runtime.types import Completion, ToolCall


def test_reported_latency_is_llm_calls_only(tmp_path: Path) -> None:
    report = run_suite(Path("evals"), work_dir=tmp_path / "suite")
    assert "(llm calls only)" in report.text
    assert "(tool steps)" in report.text
    case_dir = tmp_path / "suite" / "hp_damaged_full" / "runtime.sqlite"
    connection = sqlite3.connect(case_dir)
    kinds = connection.execute("select kind from steps where latency_us is not null").fetchall()
    connection.close()
    result = next(item for item in report.results if item.case_id == "hp_damaged_full")
    llm = [kind for (kind,) in kinds if kind == "llm"]
    tools = [kind for (kind,) in kinds if kind == "tool"]
    assert llm
    assert tools
    assert len(result.latency_us) == len(llm)
    assert len(result.tool_latency_us) == len(tools)


def test_human_reject_allows_a_parallel_email_proposal(tmp_path: Path) -> None:
    case = _case("edge_human_reject")
    final = json.dumps(
        {
            "amount_cents": None,
            "customer_summary": "A reviewer rejected the refund. No money moved.",
            "order_id": "LG-1001",
            "outcome": "refund_rejected",
        }
    )
    completions = (
        _call("lookup_order", {"order_id": "LG-1001"}),
        _call("lookup_policy", {"reason": "damaged"}),
        Completion(
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_refund",
                    name="send_refund",
                    arguments={
                        "amount_cents": 4200,
                        "order_id": "LG-1001",
                        "reason": "damaged",
                    },
                ),
                ToolCall(
                    id="call_email",
                    name="send_email",
                    arguments={
                        "body": "We received your request.",
                        "order_id": "LG-1001",
                        "subject": "Request",
                        "to": "avery.chen@lumen-goods.example",
                    },
                ),
            ),
            tokens_in=4,
            tokens_out=8,
        ),
        Completion(content=final, tool_calls=(), tokens_in=4, tokens_out=8),
    )
    result = _run_case(case, CassetteProvider(completions), Config.from_env({}), tmp_path)
    assert result.passed, result.deterministic_failures + result.check_failures
    assert result.tools == [
        "lookup_order",
        "lookup_policy",
        "send_refund",
        "send_email",
    ]
    assert result.tools != list(case.tools)


def test_unknown_order_can_take_an_extra_lookup(tmp_path: Path) -> None:
    case = _case("edge_not_found")
    final = json.dumps(
        {
            "amount_cents": None,
            "customer_summary": "No order exists with that id.",
            "order_id": "LG-1999",
            "outcome": "denied",
        }
    )
    completions = (
        _call("lookup_order", {"order_id": "LG-1999"}),
        _call("lookup_policy", {"reason": "damaged"}),
        Completion(content=final, tool_calls=(), tokens_in=4, tokens_out=8),
    )
    result = _run_case(case, CassetteProvider(completions), Config.from_env({}), tmp_path)
    assert result.passed, result.deterministic_failures + result.check_failures
    assert "lookup_policy" in result.tools


def test_zero_amount_false_claim_fails_the_case(tmp_path: Path) -> None:
    case = _case("edge_zero_amount")
    final = json.dumps(
        {
            "amount_cents": None,
            "customer_summary": "Your refund of 0 cents was processed.",
            "order_id": "LG-1001",
            "outcome": "denied",
        }
    )
    email = ToolCall(
        id="call_email",
        name="send_email",
        arguments={
            "body": "Your refund of 0 cents was processed.",
            "order_id": "LG-1001",
            "subject": "Refund",
            "to": "avery.chen@lumen-goods.example",
        },
    )
    completions = (
        _call("lookup_order", {"order_id": "LG-1001"}),
        _call("lookup_policy", {"reason": "damaged"}),
        Completion(content=None, tool_calls=(email,), tokens_in=4, tokens_out=8),
        Completion(content=final, tool_calls=(), tokens_in=4, tokens_out=8),
    )
    result = _run_case(case, CassetteProvider(completions), Config.from_env({}), tmp_path)
    assert not result.passed
    assert any("needs_review" in item for item in result.deterministic_failures)


def _case(case_id: str):
    return next(case for case in load_cases(Path("evals/cases.json")) if case.id == case_id)


def _call(name: str, arguments: dict[str, object]) -> Completion:
    return Completion(
        content=None,
        tool_calls=(ToolCall(id=f"call_{name}", name=name, arguments=arguments),),
        tokens_in=4,
        tokens_out=4,
    )
