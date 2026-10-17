"""OpenAI-compatible chat completions over stdlib HTTP.

xAI (Grok) and OpenAI both speak this shape. The provider name, base URL,
model, and API key come from the environment. This module is not used by
CI. It has not been run against the real xAI or OpenAI APIs.
"""

from __future__ import annotations

from agent_runtime.config import LiveSettings
from agent_runtime.errors import PermanentError, ValidationError
from agent_runtime.jsonutil import as_dict, as_int, as_list, as_str, dumps, loads
from agent_runtime.pricing import estimate_tokens
from agent_runtime.prompts import TOOL_NAMES
from agent_runtime.providers.http import Transport, read_json
from agent_runtime.providers.live_call import LiveCall
from agent_runtime.providers.spend import SpendLedger
from agent_runtime.providers.tool_schema import parameter_object
from agent_runtime.types import Completion, CompletionRequest, Message, ToolCall


class OpenAICompatibleProvider:
    name: str

    def __init__(
        self,
        *,
        name: str,
        settings: LiveSettings,
        transport: Transport,
        ledger: SpendLedger,
    ) -> None:
        self.name = name
        self._settings = settings
        self._transport = transport
        self._call = LiveCall(
            provider=name,
            model=settings.model,
            price_date=settings.price_date,
            input_micro_usd_per_million=settings.input_micro_usd_per_million,
            output_micro_usd_per_million=settings.output_micro_usd_per_million,
            ledger=ledger,
        )

    def complete(self, request: CompletionRequest) -> Completion:
        started = self._call.begin(request.run_id)
        body = dumps(_request_body(self._settings, request)).encode("utf-8")
        response = self._transport.post(
            f"{self._settings.base_url}/chat/completions",
            {
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json",
            },
            body,
            self._settings.timeout_s,
        )
        payload = read_json(response)
        content, calls, tokens_in, tokens_out = _parse_completion(payload)
        cost = self._call.finish(request.run_id, response.status, tokens_in, tokens_out, started)
        return Completion(
            content=content,
            tool_calls=tuple(calls),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_micro_usd=cost,
        )


def _request_body(settings: LiveSettings, request: CompletionRequest) -> dict[str, object]:
    return {
        "model": settings.model,
        "max_tokens": settings.max_output_tokens,
        "messages": [_wire_message(message) for message in request.messages],
        "tools": [
            {
                "type": "function",
                "function": {"name": name, "parameters": parameter_object(name)},
            }
            for name in TOOL_NAMES
            if name in request.tool_names
        ],
    }


def _wire_message(message: Message) -> dict[str, object]:
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": dumps(call.arguments)},
                }
                for call in message.tool_calls
            ],
        }
    return {"role": message.role, "content": message.content}


def _parse_completion(
    payload: dict[str, object],
) -> tuple[str | None, list[ToolCall], int, int]:
    choices = as_list(payload.get("choices"), "choices")
    if not choices:
        raise PermanentError("model response had no choices")
    choice = as_dict(choices[0])
    message = as_dict(choice.get("message"))
    content_value = message.get("content")
    content = None if content_value is None else as_str(content_value, "content")
    calls: list[ToolCall] = []
    raw_calls = message.get("tool_calls")
    if raw_calls is not None:
        for item in as_list(raw_calls, "tool_calls"):
            call = as_dict(item)
            function = as_dict(call.get("function"))
            try:
                arguments = as_dict(loads(as_str(function.get("arguments"), "arguments")))
            except ValidationError as exc:
                raise PermanentError("model tool arguments were not a JSON object") from exc
            calls.append(
                ToolCall(
                    id=as_str(call.get("id"), "id"),
                    name=as_str(function.get("name"), "name"),
                    arguments=arguments,
                )
            )
    tokens_in, tokens_out = _usage(payload, content, calls)
    return content, calls, tokens_in, tokens_out


def _usage(
    payload: dict[str, object], content: str | None, calls: list[ToolCall]
) -> tuple[int, int]:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        usage_dict = as_dict(usage)
        return (
            as_int(usage_dict.get("prompt_tokens"), "prompt_tokens"),
            as_int(usage_dict.get("completion_tokens"), "completion_tokens"),
        )
    output = content or ""
    for call in calls:
        output = f"{output}\n{call.name}\n{dumps(call.arguments)}"
    return estimate_tokens(output), estimate_tokens(output)
