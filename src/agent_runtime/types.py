"""Records the rest of the runtime passes around.

Frozen on purpose: a step is changed by writing a new row, not by mutating
a shared object in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_runtime.errors import StoreError
from agent_runtime.jsonutil import as_dict, as_int, as_list, as_str, dumps, loads

RunStatus = Literal["running", "waiting_review", "completed", "failed", "interrupted"]
StepStatus = Literal["running", "succeeded", "failed", "waiting_review", "rejected", "approved"]
StepKind = Literal["llm", "tool"]
Role = Literal["system", "user", "assistant", "tool"]

RUN_STATUSES: frozenset[str] = frozenset(
    {"running", "waiting_review", "completed", "failed", "interrupted"}
)
STEP_STATUSES: frozenset[str] = frozenset(
    {"running", "succeeded", "failed", "waiting_review", "rejected", "approved"}
)
FINAL_OUTCOMES: frozenset[str] = frozenset(
    {"refund_completed", "denied", "status_only", "needs_ops", "refund_rejected"}
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class Completion:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    tokens_in: int
    tokens_out: int
    # Set by a hosted provider from the operator's price table. The stub
    # leaves this empty so the runner keeps using the synthetic stub price.
    cost_micro_usd: int | None = None


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class CompletionRequest:
    messages: tuple[Message, ...]
    tool_names: tuple[str, ...]
    run_id: str = ""


@dataclass(frozen=True)
class RunRecord:
    id: str
    status: RunStatus
    input_json: str
    output_json: str | None
    budget_micro_usd: int
    spent_micro_usd: int
    consecutive_failures: int
    created_at: str
    updated_at: str
    error: str | None


@dataclass(frozen=True)
class StepRecord:
    id: str
    run_id: str
    seq: int
    kind: StepKind
    name: str
    status: StepStatus
    input_json: str
    output_json: str | None
    idempotency_key: str
    attempt: int
    max_attempts: int
    latency_us: int | None
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int
    error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PendingReview:
    step_id: str
    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    status: RunStatus
    output: dict[str, object] | None
    pending: tuple[PendingReview, ...]
    error: str | None
    spent_micro_usd: int
    tokens_in: int
    tokens_out: int


def require_run_status(value: str) -> RunStatus:
    if value not in RUN_STATUSES:
        raise StoreError(f"unknown run status: {value}")
    return value  # type: ignore[return-value]


def require_step_status(value: str) -> StepStatus:
    if value not in STEP_STATUSES:
        raise StoreError(f"unknown step status: {value}")
    return value  # type: ignore[return-value]


def require_step_kind(value: str) -> StepKind:
    if value not in ("llm", "tool"):
        raise StoreError(f"unknown step kind: {value}")
    return value  # type: ignore[return-value]


def encode_completion(completion: Completion) -> str:
    payload: dict[str, object] = {
        "content": completion.content,
        "tokens_in": completion.tokens_in,
        "tokens_out": completion.tokens_out,
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in completion.tool_calls
        ],
    }
    return dumps(payload)


def decode_completion(text: str) -> Completion:
    raw = as_dict(loads(text))
    content_value = raw.get("content")
    content = None if content_value is None else as_str(content_value, "content")
    calls: list[ToolCall] = []
    for item in as_list(raw.get("tool_calls"), "tool_calls"):
        call = as_dict(item)
        calls.append(
            ToolCall(
                id=as_str(call.get("id"), "id"),
                name=as_str(call.get("name"), "name"),
                arguments=as_dict(call.get("arguments")),
            )
        )
    return Completion(
        content=content,
        tool_calls=tuple(calls),
        tokens_in=as_int(raw.get("tokens_in"), "tokens_in"),
        tokens_out=as_int(raw.get("tokens_out"), "tokens_out"),
    )
