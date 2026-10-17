"""Load the golden set. The files are the contract; the runner does not invent cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_runtime.jsonutil import as_dict, as_int, as_list, as_str, dumps, loads, optional_int
from agent_runtime.types import Completion, decode_completion

GateDecision = Literal["approve", "reject"]


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    title: str
    case_input: dict[str, object]
    tools: tuple[str, ...]
    outcome: str
    amount_cents: int | None
    requires_human_gate: tuple[str, ...]
    refund_effects: int
    email_effects: int
    gate_decision: GateDecision = "approve"


def load_cases(path: Path) -> tuple[EvalCase, ...]:
    raw = as_list(loads(path.read_text(encoding="utf-8")), "cases")
    cases = tuple(_case(item) for item in raw)
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate eval case id")
    return cases


def load_cassette(path: Path) -> tuple[Completion, ...]:
    payload = as_dict(loads(path.read_text(encoding="utf-8")))
    completions: list[Completion] = []
    for item in as_list(payload.get("completions"), "completions"):
        completions.append(decode_completion(dumps(as_dict(item))))
    if not completions:
        raise ValueError(f"cassette is empty: {path}")
    return tuple(completions)


def dump_cassette(
    case_id: str,
    completions: tuple[Completion, ...],
    model: str = "stub-llm-v1",
    provider: str = "fake",
) -> str:
    payload: dict[str, object] = {
        "case_id": case_id,
        "model": model,
        "provider": provider,
        "completions": [_completion_obj(completion) for completion in completions],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _completion_obj(completion: Completion) -> dict[str, object]:
    return {
        "content": completion.content,
        "tokens_in": completion.tokens_in,
        "tokens_out": completion.tokens_out,
        "tool_calls": [
            {"arguments": call.arguments, "id": call.id, "name": call.name}
            for call in completion.tool_calls
        ],
    }


def _case(value: object) -> EvalCase:
    raw = as_dict(value)
    tools = tuple(as_str(item, "tools") for item in as_list(raw.get("tools"), "tools"))
    gates = tuple(
        as_str(item, "requires_human_gate")
        for item in as_list(raw.get("requires_human_gate"), "requires_human_gate")
    )
    category = as_str(raw.get("category"), "category")
    if category not in ("happy", "edge", "adversarial"):
        raise ValueError(f"bad category on {raw.get('id')}")
    return EvalCase(
        id=as_str(raw.get("id"), "id"),
        category=category,
        title=as_str(raw.get("title"), "title"),
        case_input=as_dict(raw.get("input")),
        tools=tools,
        outcome=as_str(raw.get("outcome"), "outcome"),
        amount_cents=optional_int(raw.get("amount_cents"), "amount_cents"),
        requires_human_gate=gates,
        refund_effects=as_int(raw.get("refund_effects"), "refund_effects"),
        email_effects=as_int(raw.get("email_effects"), "email_effects"),
        gate_decision=_gate_decision(raw.get("gate_decision", "approve")),
    )


def _gate_decision(value: object) -> GateDecision:
    if value == "approve":
        return "approve"
    if value == "reject":
        return "reject"
    raise ValueError("gate_decision must be approve or reject")
