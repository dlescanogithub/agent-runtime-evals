"""Thin adapter for the Anthropic Messages API.

Not the provider CI uses. Untested against the real Anthropic API. Enable
it only with LIVE_MODE=1 and a key loaded as a secret. The request follows
the public Messages API and sends the documented version header
``anthropic-version: 2023-06-01``. That header is an API version, not a secret.
"""

from __future__ import annotations

from agent_runtime.config import LiveSettings
from agent_runtime.errors import PermanentError
from agent_runtime.jsonutil import as_dict, as_list, as_str, dumps
from agent_runtime.pricing import estimate_tokens
from agent_runtime.prompts import TOOL_DESCRIPTIONS, TOOL_NAMES
from agent_runtime.providers.http import Transport, read_json
from agent_runtime.providers.live_call import LiveCall
from agent_runtime.providers.spend import SpendLedger
from agent_runtime.providers.tool_schema import parameter_object
from agent_runtime.providers.usage import UsageBill, bill_from_anthropic_usage
from agent_runtime.types import Completion, CompletionRequest, Message, ToolCall

_API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        settings: LiveSettings,
        transport: Transport,
        ledger: SpendLedger,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._call = LiveCall(
            provider=self.name,
            model=settings.model,
            price_date=settings.price_date,
            input_micro_usd_per_million=settings.input_micro_usd_per_million,
            output_micro_usd_per_million=settings.output_micro_usd_per_million,
            cached_input_micro_usd_per_million=settings.cached_input_micro_usd_per_million,
            ledger=ledger,
        )

    def complete(self, request: CompletionRequest) -> Completion:
        started = self._call.begin(request.run_id)
        response = self._transport.post(
            f"{self._settings.base_url}/v1/messages",
            {
                "x-api-key": self._settings.api_key,
                "anthropic-version": _API_VERSION,
                "Content-Type": "application/json",
            },
            dumps(_request_body(self._settings, request)).encode("utf-8"),
            self._settings.timeout_s,
        )
        payload = read_json(response)
        content, calls, bill = _parse_message(payload)
        cost = self._call.finish(request.run_id, response.status, bill, started)
        return Completion(
            content=content,
            tool_calls=tuple(calls),
            tokens_in=bill.tokens_in,
            tokens_out=bill.tokens_out,
            cost_micro_usd=cost,
        )


def _request_body(settings: LiveSettings, request: CompletionRequest) -> dict[str, object]:
    system_parts: list[str] = []
    messages: list[dict[str, object]] = []
    pending_tools: list[dict[str, object]] = []

    def flush_tools() -> None:
        if pending_tools:
            messages.append({"role": "user", "content": list(pending_tools)})
            pending_tools.clear()

    for message in request.messages:
        if message.role == "system":
            flush_tools()
            system_parts.append(message.content)
            continue
        if message.role == "tool":
            if not message.tool_call_id:
                raise PermanentError("tool message is missing tool_call_id")
            pending_tools.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        flush_tools()
        if message.role == "assistant":
            messages.append({"role": "assistant", "content": _assistant_blocks(message)})
            continue
        if message.role == "user":
            messages.append({"role": "user", "content": message.content})
            continue
        raise PermanentError("unsupported message role")
    flush_tools()
    body: dict[str, object] = {
        "model": settings.model,
        "max_tokens": settings.max_output_tokens,
        "messages": messages,
        "tools": [
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "input_schema": parameter_object(name),
            }
            for name in TOOL_NAMES
            if name in request.tool_names
        ],
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)
    return body


def _assistant_blocks(message: Message) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls:
        blocks.append(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        )
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    return blocks


def _parse_message(
    payload: dict[str, object],
) -> tuple[str | None, list[ToolCall], UsageBill]:
    texts: list[str] = []
    calls: list[ToolCall] = []
    for item in as_list(payload.get("content"), "content"):
        block = as_dict(item)
        kind = as_str(block.get("type"), "type")
        if kind == "text":
            texts.append(as_str(block.get("text"), "text"))
        elif kind == "tool_use":
            calls.append(
                ToolCall(
                    id=as_str(block.get("id"), "id"),
                    name=as_str(block.get("name"), "name"),
                    arguments=as_dict(block.get("input")),
                )
            )
    content = "\n".join(texts) if texts else None
    return content, calls, _usage(payload, content, calls)


def _usage(payload: dict[str, object], content: str | None, calls: list[ToolCall]) -> UsageBill:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        return bill_from_anthropic_usage(as_dict(usage))
    output = content or ""
    for call in calls:
        output = f"{output}\n{call.name}\n{dumps(call.arguments)}"
    tokens = estimate_tokens(output)
    return UsageBill(
        tokens_in=tokens,
        tokens_out=tokens,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_ticks=None,
        reasoning_assumed_extra=False,
    )
