"""Thin client for any API that speaks the OpenAI chat-completions shape.

Not used by tests, the demo, or CI. There is no SDK dependency: the standard
library sends one HTTP POST. The API key is a header and is never logged.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Protocol

from agent_runtime.errors import PermanentError, TransientError, ValidationError
from agent_runtime.jsonutil import as_dict, as_int, as_list, as_str, dumps, loads
from agent_runtime.pricing import estimate_tokens
from agent_runtime.prompts import TOOL_NAMES
from agent_runtime.types import Completion, CompletionRequest, Message, ToolCall

_RETRYABLE = frozenset({408, 409, 429, 500, 502, 503, 504})


class HttpResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body


class Transport(Protocol):
    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        """Send one POST. Raise TransientError when the network itself fails."""


class UrllibTransport:
    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read()
                status = response.status
                if not isinstance(status, int):
                    raise PermanentError("response status was not an integer")
                return HttpResponse(status=status, body=raw)
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read())
        except urllib.error.URLError as exc:
            raise TransientError("model endpoint was unreachable") from exc


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: float,
        transport: Transport,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport

    def complete(self, request: CompletionRequest) -> Completion:
        body = dumps(_request_body(self._model, request))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        response = self._transport.post(
            f"{self._base_url}/chat/completions",
            headers,
            body.encode("utf-8"),
            self._timeout_s,
        )
        if response.status in _RETRYABLE:
            raise TransientError(f"model endpoint returned HTTP {response.status}")
        if response.status != 200:
            raise PermanentError(f"model endpoint returned HTTP {response.status}")
        try:
            payload = as_dict(loads(response.body.decode("utf-8")))
        except (UnicodeDecodeError, ValidationError) as exc:
            raise PermanentError("model endpoint returned invalid JSON") from exc
        return _parse_completion(payload)


def _request_body(model: str, request: CompletionRequest) -> dict[str, object]:
    return {
        "model": model,
        "messages": [_wire_message(message) for message in request.messages],
        "tools": [_tool_schema(name) for name in TOOL_NAMES if name in request.tool_names],
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
                    "function": {
                        "name": call.name,
                        "arguments": dumps(call.arguments),
                    },
                }
                for call in message.tool_calls
            ],
        }
    return {"role": message.role, "content": message.content}


def _tool_schema(name: str) -> dict[str, object]:
    properties: dict[str, object]
    required: list[str]
    if name == "lookup_order":
        properties = {"order_id": {"type": "string"}}
        required = ["order_id"]
    elif name == "lookup_policy":
        properties = {"reason": {"type": "string"}}
        required = ["reason"]
    elif name == "send_refund":
        properties = {
            "order_id": {"type": "string"},
            "amount_cents": {"type": "integer"},
            "reason": {"type": "string"},
        }
        required = ["order_id", "amount_cents", "reason"]
    else:
        properties = {
            "order_id": {"type": "string"},
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        }
        required = ["order_id", "to", "subject", "body"]
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _parse_completion(payload: dict[str, object]) -> Completion:
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
            arguments = as_dict(loads(as_str(function.get("arguments"), "arguments")))
            calls.append(
                ToolCall(
                    id=as_str(call.get("id"), "id"),
                    name=as_str(function.get("name"), "name"),
                    arguments=arguments,
                )
            )
    tokens_in, tokens_out = _usage(payload, content, calls)
    return Completion(
        content=content,
        tool_calls=tuple(calls),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


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
