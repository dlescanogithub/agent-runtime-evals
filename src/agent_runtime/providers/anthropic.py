"""Thin adapter for the Anthropic Messages API.

Not the provider CI uses. Untested against the real Anthropic API. Enable
it only with LIVE_MODE=1 and a key loaded as a secret. The request follows
the public Messages API and sends the documented version header
``anthropic-version: 2023-06-01``. That header is an API version, not a secret.
"""

from __future__ import annotations

from agent_runtime.config import LiveSettings
from agent_runtime.errors import PermanentError
from agent_runtime.jsonutil import as_dict, as_int, as_list, as_str, dumps
from agent_runtime.pricing import estimate_tokens
from agent_runtime.prompts import TOOL_NAMES
from agent_runtime.providers.http import Transport, read_json
from agent_runtime.providers.live_call import LiveCall
from agent_runtime.providers.spend import SpendLedger
from agent_runtime.providers.tool_schema import parameter_object
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
        content, calls, tokens_in, tokens_out = _parse_message(payload)
        cost = self._call.finish(request.run_id, response.status, tokens_in, tokens_out, started)
        return Completion(
            content=content,
            tool_calls=tuple(calls),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
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
            {"name": name, "input_schema": parameter_object(name)}
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
) -> tuple[str | None, list[ToolCall], int, int]:
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
    tokens_in, tokens_out = _usage(payload, content, calls)
    return content, calls, tokens_in, tokens_out


def _usage(
    payload: dict[str, object], content: str | None, calls: list[ToolCall]
) -> tuple[int, int]:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        usage_dict = as_dict(usage)
        return (
            as_int(usage_dict.get("input_tokens"), "input_tokens"),
            as_int(usage_dict.get("output_tokens"), "output_tokens"),
        )
    output = content or ""
    for call in calls:
        output = f"{output}\n{call.name}\n{dumps(call.arguments)}"
    return estimate_tokens(output), estimate_tokens(output)
