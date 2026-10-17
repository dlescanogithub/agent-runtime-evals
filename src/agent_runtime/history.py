"""Rebuild the model transcript from the ledger.

The messages are not a second source of truth. After a crash the runner
loads the steps and continues. If this function and the runner disagree
about which steps are visible, resume will double-call the model.
"""

from __future__ import annotations

from agent_runtime.jsonutil import as_dict, as_str, loads
from agent_runtime.prompts import SYSTEM_PROMPT, TOOL_NAMES
from agent_runtime.types import CompletionRequest, Message, StepRecord, decode_completion


def build_request(user_json: str, steps: list[StepRecord]) -> CompletionRequest:
    messages: list[Message] = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_json),
    ]
    for step in steps:
        if step.output_json is None:
            continue
        if step.kind == "llm" and step.status == "succeeded":
            completion = decode_completion(step.output_json)
            messages.append(
                Message(
                    role="assistant",
                    content=completion.content or "",
                    tool_calls=completion.tool_calls,
                )
            )
        elif step.kind == "tool" and step.status in ("succeeded", "rejected", "failed"):
            payload = as_dict(loads(step.input_json))
            messages.append(
                Message(
                    role="tool",
                    content=step.output_json,
                    tool_call_id=as_str(payload.get("tool_call_id"), "tool_call_id"),
                )
            )
    return CompletionRequest(messages=tuple(messages), tool_names=TOOL_NAMES)
