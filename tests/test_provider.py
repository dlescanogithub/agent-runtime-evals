import json

import pytest

from agent_runtime.errors import PermanentError, TransientError
from agent_runtime.prompts import SYSTEM_PROMPT
from agent_runtime.providers.openai_compatible import HttpResponse, OpenAICompatibleProvider
from agent_runtime.types import CompletionRequest, Message


class _Transport:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self.payload = payload
        self.headers: dict[str, str] = {}
        self.body = b""

    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        self.headers = headers
        self.body = body
        return HttpResponse(self.status, json.dumps(self.payload).encode("utf-8"))


def _request() -> CompletionRequest:
    return CompletionRequest(
        messages=(
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content="{}"),
        ),
        tool_names=("lookup_order",),
    )


def test_openai_compatible_parses_a_tool_call_and_hides_the_key() -> None:
    transport = _Transport(
        200,
        {
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "lookup_order",
                                    "arguments": '{"order_id":"LG-1001"}',
                                },
                            }
                        ],
                    }
                }
            ],
        },
    )
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="gpt-test",
        timeout_s=5,
        transport=transport,
    )
    completion = provider.complete(_request())
    assert completion.tool_calls[0].name == "lookup_order"
    assert completion.tool_calls[0].arguments == {"order_id": "LG-1001"}
    assert completion.tokens_in == 11
    assert transport.headers["Authorization"] == "Bearer test-key"
    assert b"test-key" not in transport.body


def test_retryable_and_permanent_http_status() -> None:
    retry = OpenAICompatibleProvider(
        "test-key", "https://example.test/v1", "m", 5, _Transport(429, {})
    )
    denied = OpenAICompatibleProvider(
        "test-key", "https://example.test/v1", "m", 5, _Transport(401, {})
    )
    with pytest.raises(TransientError):
        retry.complete(_request())
    with pytest.raises(PermanentError):
        denied.complete(_request())
