"""Hosted providers against an injected transport. No network and no real key."""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent_runtime.config import Config, LiveSettings
from agent_runtime.demo import DEMO_INPUT
from agent_runtime.errors import ConfigError, PermanentError, SpendCapError, TransientError
from agent_runtime.prompts import SYSTEM_PROMPT
from agent_runtime.providers import build_provider
from agent_runtime.providers.anthropic import AnthropicProvider
from agent_runtime.providers.http import HttpResponse, UrllibTransport
from agent_runtime.providers.openai_compatible import OpenAICompatibleProvider
from agent_runtime.providers.spend import SpendLedger, reset_process_spend
from agent_runtime.store import SQLiteStore
from agent_runtime.types import CompletionRequest, Message, ToolCall
from agent_runtime.wiring import build_runner

_FINAL = (
    '{"amount_cents":null,"customer_summary":"No refund.","order_id":"LG-1001","outcome":"denied"}'
)


class _Transport:
    def __init__(
        self,
        status: int,
        payload: dict[str, object],
        response_headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.payload = payload
        self.response_headers = response_headers or {}
        self.headers: dict[str, str] = {}
        self.body = b""
        self.url = ""
        self.posts = 0

    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        self.posts += 1
        self.url = url
        self.headers = headers
        self.body = body
        return HttpResponse(
            self.status,
            json.dumps(self.payload).encode("utf-8"),
            headers=self.response_headers,
        )


def _settings(
    *,
    base_url: str = "https://example.test/v1",
) -> LiveSettings:
    return LiveSettings(
        api_key="test-key",
        base_url=base_url,
        model="model-under-test",
        timeout_s=5.0,
        max_output_tokens=32,
        price_date="2026-01-15",
        input_micro_usd_per_million=1_000_000,
        output_micro_usd_per_million=2_000_000,
        cached_input_micro_usd_per_million=None,
        max_spend_micro_usd=1_000_000,
    )


def _request(run_id: str = "run-1") -> CompletionRequest:
    return CompletionRequest(
        messages=(
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content="customer-secret-phrase"),
            Message(
                role="assistant",
                content="",
                tool_calls=(
                    ToolCall(id="call_0", name="lookup_order", arguments={"order_id": "LG-1001"}),
                ),
            ),
            Message(role="tool", content="{}", tool_call_id="call_0"),
        ),
        tool_names=("lookup_order", "send_refund"),
        run_id=run_id,
    )


def _openai_payload() -> dict[str, object]:
    return {
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
    }


def _provider(
    transport: _Transport, *, name: str = "xai", cap: int = 1_000_000
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        settings=_settings(),
        transport=transport,
        ledger=SpendLedger(cap),
    )


@pytest.fixture(autouse=True)
def _reset_spend() -> None:
    reset_process_spend()


def test_openai_compatible_parses_a_tool_call_and_hides_the_key() -> None:
    transport = _Transport(200, _openai_payload())
    completion = _provider(transport).complete(_request())
    body = json.loads(transport.body)
    assert completion.tool_calls[0].arguments == {"order_id": "LG-1001"}
    assert completion.tokens_in == 11
    assert completion.cost_micro_usd == 25
    assert transport.url == "https://example.test/v1/chat/completions"
    assert transport.headers["Authorization"] == "Bearer test-key"
    assert b"test-key" not in transport.body
    assert body["max_tokens"] == 32
    descriptions = [tool["function"]["description"] for tool in body["tools"]]
    assert descriptions
    assert all(isinstance(item, str) and item for item in descriptions)
    assert body["messages"][2]["tool_calls"][0]["function"]["name"] == "lookup_order"
    assert body["messages"][3]["role"] == "tool"


def test_a_429_logs_http_status_and_keeps_retry_after(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agent_runtime.providers")
    provider = _provider(_Transport(429, {}, response_headers={"Retry-After": "1.5"}))
    with pytest.raises(TransientError) as caught:
        provider.complete(_request())
    assert caught.value.http_status == 429
    assert caught.value.retry_after_s == 1.5
    statuses = [getattr(record, "extra_fields", {}).get("http_status") for record in caplog.records]
    assert 429 in statuses


def test_retryable_permanent_and_invalid_payloads() -> None:
    request = _request()
    retry = _provider(_Transport(429, {}))
    denied = _provider(_Transport(401, {}))
    broken = _provider(_Transport(200, {"choices": []}))
    garbage = OpenAICompatibleProvider(
        name="openai",
        settings=_settings(),
        transport=_Bytes(200, b"not-json"),
        ledger=SpendLedger(1_000_000),
    )
    bad_args = _provider(
        _Transport(
            200,
            {
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {"name": "lookup_order", "arguments": "[]"},
                                }
                            ],
                        }
                    }
                ],
            },
        )
    )
    with pytest.raises(TransientError):
        retry.complete(request)
    with pytest.raises(PermanentError):
        denied.complete(request)
    with pytest.raises(PermanentError):
        broken.complete(request)
    with pytest.raises(PermanentError):
        garbage.complete(request)
    with pytest.raises(PermanentError):
        bad_args.complete(request)


def test_missing_usage_falls_back_to_the_character_estimate() -> None:
    transport = _Transport(
        200,
        {"choices": [{"message": {"content": "abcd", "tool_calls": None}}]},
    )
    completion = _provider(transport).complete(_request())
    assert completion.tokens_in == 1
    assert completion.tokens_out == 1
    assert completion.content == "abcd"


def test_spend_cap_stops_a_run_and_the_process(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="agent_runtime.providers")
    transport = _Transport(200, _openai_payload())
    provider = _provider(transport, cap=30)
    first = provider.complete(_request("run-a"))
    assert first.cost_micro_usd == 25
    with pytest.raises(SpendCapError, match="Hard stop"):
        provider.complete(_request("run-a"))
    assert transport.posts == 2
    with pytest.raises(SpendCapError, match="already reached"):
        provider.complete(_request("run-b"))
    assert transport.posts == 2
    blob = _log_blob(caplog)
    assert "test-key" not in blob
    assert "customer-secret-phrase" not in blob
    assert "Bearer" not in blob
    fields = caplog.records[-1].extra_fields  # type: ignore[attr-defined]
    assert fields["provider"] == "xai"
    assert fields["model"] == "model-under-test"
    assert fields["price_date"] == "2026-01-15"
    assert "content" not in fields


def test_a_second_run_shares_the_process_cap() -> None:
    transport = _Transport(200, _openai_payload())
    provider = _provider(transport, cap=30)
    provider.complete(_request("run-a"))
    with pytest.raises(SpendCapError, match="process spent"):
        provider.complete(_request("run-b"))


def test_live_call_requires_a_run_id() -> None:
    transport = _Transport(200, _openai_payload())
    with pytest.raises(PermanentError, match="run_id"):
        _provider(transport).complete(_request(""))
    assert transport.posts == 0


def test_anthropic_adapter_maps_messages_and_hides_the_key() -> None:
    transport = _Transport(
        200,
        {
            "usage": {"input_tokens": 11, "output_tokens": 7},
            "content": [
                {"type": "text", "text": "looking"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "lookup_order",
                    "input": {"order_id": "LG-1001"},
                },
            ],
        },
    )
    provider = AnthropicProvider(
        settings=_settings(base_url="https://example.test"),
        transport=transport,
        ledger=SpendLedger(1_000_000),
    )
    completion = provider.complete(_request())
    body = json.loads(transport.body)
    assert provider.name == "anthropic"
    assert completion.tool_calls[0].name == "lookup_order"
    assert completion.content == "looking"
    assert completion.cost_micro_usd == 25
    assert transport.url == "https://example.test/v1/messages"
    assert transport.headers["x-api-key"] == "test-key"
    assert transport.headers["anthropic-version"] == "2023-06-01"
    assert b"test-key" not in transport.body
    assert body["system"] == SYSTEM_PROMPT
    assert [message["role"] for message in body["messages"]] == ["user", "assistant", "user"]
    tool_results = body["messages"][2]["content"]
    assert tool_results[0]["type"] == "tool_result"
    assert tool_results[0]["tool_use_id"] == "call_0"
    assert body["messages"][1]["content"][0]["type"] == "tool_use"


def test_anthropic_without_usage_estimates_tokens() -> None:
    transport = _Transport(
        200,
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t",
                    "name": "lookup_order",
                    "input": {"order_id": "LG-1"},
                }
            ]
        },
    )
    provider = AnthropicProvider(
        settings=_settings(), transport=transport, ledger=SpendLedger(1_000_000)
    )
    completion = provider.complete(_request())
    assert completion.content is None
    assert completion.tokens_in >= 1


def test_runner_records_the_operator_price(config: Config) -> None:
    transport = _Transport(
        200,
        {
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            "choices": [{"message": {"content": _FINAL}}],
        },
    )
    provider = _provider(transport)
    done = build_runner(config, provider=provider).start(DEMO_INPUT)
    assert done.status == "completed"
    assert done.spent_micro_usd == 25
    assert SQLiteStore(config.database_path).count_effects("send_refund") == 0


def test_runner_stops_when_the_live_cap_is_crossed(config: Config) -> None:
    transport = _Transport(
        200,
        {
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            "choices": [{"message": {"content": _FINAL}}],
        },
    )
    done = build_runner(config, provider=_provider(transport, cap=1)).start(DEMO_INPUT)
    assert done.status == "failed"
    assert done.error is not None
    assert "live spend cap" in done.error
    assert SQLiteStore(config.database_path).count_effects("send_refund") == 0


def test_build_provider_selects_the_named_client() -> None:
    transport = _Transport(200, _openai_payload())
    xai = build_provider(
        Config.from_env(_live_env("xai")), transport=transport, ledger=SpendLedger(100)
    )
    openai = build_provider(
        Config.from_env(_live_env("openai")), transport=transport, ledger=SpendLedger(100)
    )
    anthropic = build_provider(
        Config.from_env(_live_env("anthropic")), transport=transport, ledger=SpendLedger(100)
    )
    assert isinstance(xai, OpenAICompatibleProvider)
    assert xai.name == "xai"
    assert isinstance(openai, OpenAICompatibleProvider)
    assert openai.name == "openai"
    assert isinstance(anthropic, AnthropicProvider)


def test_a_second_process_cap_is_rejected() -> None:
    build_provider(Config.from_env(_live_env("xai", MAX_LIVE_SPEND_USD="1.00")))
    again = build_provider(Config.from_env(_live_env("openai", MAX_LIVE_SPEND_USD="1.00")))
    assert again.name == "openai"
    with pytest.raises(ConfigError, match="cannot change"):
        build_provider(Config.from_env(_live_env("xai", MAX_LIVE_SPEND_USD="2.00")))


def test_build_provider_refuses_a_mismatched_config() -> None:
    hosted = Config.from_env(_live_env("xai"))
    with pytest.raises(ConfigError, match="not valid"):
        build_provider(replace(hosted, llm_provider="fake"))
    with pytest.raises(ConfigError, match="LIVE_MODE=1 is required"):
        build_provider(replace(hosted, live=None))


def test_urllib_transport_talks_only_to_localhost() -> None:
    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]
    try:
        transport = UrllibTransport()
        ok = transport.post(
            f"http://127.0.0.1:{port}/ok",
            {"Content-Type": "application/json"},
            b"{}",
            2,
        )
        denied = transport.post(f"http://127.0.0.1:{port}/deny", {}, b"{}", 2)
        assert ok.status == 200
        assert ok.body == b'{"ok":true}'
        assert denied.status == 401
        assert server.last_body == b"{}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(TransientError):
        UrllibTransport().post(f"http://127.0.0.1:{closed_port}/x", {}, b"{}", 1)


class _Bytes:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.raw = body

    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        return HttpResponse(self.status, self.raw)


class _Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.last_body = b""


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        server = self.server
        if isinstance(server, _Server):
            server.last_body = body
        if self.path == "/deny":
            payload = b"{}"
            self.send_response(401)
        else:
            payload = b'{"ok":true}'
            self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _live_env(provider: str, **overrides: str) -> dict[str, str]:
    env = {
        "LLM_PROVIDER": provider,
        "LIVE_MODE": "1",
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.test/v1",
        "LLM_MODEL": "model-under-test",
        "LLM_PRICE_DATE": "2026-01-15",
        "LLM_INPUT_USD_PER_MILLION": "1.00",
        "LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MAX_LIVE_SPEND_USD": "1.00",
    }
    env.update(overrides)
    return env


def _log_blob(caplog: pytest.LogCaptureFixture) -> str:
    extras: list[object] = []
    for record in caplog.records:
        extras.append(getattr(record, "extra_fields", {}))
    return caplog.text + json.dumps(extras)
