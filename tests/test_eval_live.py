"""eval-live fails closed and never writes the committed cassettes."""

import json
import time
from pathlib import Path

import pytest

from agent_runtime.errors import ConfigError
from agent_runtime.evalkit.__main__ import main as eval_main
from agent_runtime.evalkit.cases import load_cassette
from agent_runtime.evalkit.suite import refuse_committed_cassettes, run_live
from agent_runtime.logging_setup import configure
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.providers.live_call import LiveCall
from agent_runtime.providers.spend import SpendLedger
from agent_runtime.providers.usage import UsageBill


def _live_env(cassette_dir: str) -> dict[str, str]:
    return {
        "LLM_PROVIDER": "xai",
        "LIVE_MODE": "1",
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.test/v1",
        "LLM_MODEL": "model-under-test",
        "LLM_PRICE_DATE": "2026-01-15",
        "LLM_INPUT_USD_PER_MILLION": "1.00",
        "LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MAX_LIVE_SPEND_USD": "1.00",
        "LIVE_CASSETTE_DIR": cassette_dir,
    }


def test_eval_live_refuses_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider was built")

    monkeypatch.setattr("agent_runtime.providers.build_provider", explode)
    monkeypatch.delenv("LIVE_MODE", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    with pytest.raises(ConfigError, match="No request was sent"):
        run_live(Path("evals"), environ={})
    assert eval_main(["live"]) == 2


def test_eval_live_refuses_to_overwrite_committed_cassettes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider was built")

    monkeypatch.setattr("agent_runtime.providers.build_provider", explode)
    with pytest.raises(ConfigError, match="committed cassette"):
        run_live(Path("evals"), environ=_live_env("evals/cassettes"))
    with pytest.raises(ConfigError, match="committed cassette"):
        refuse_committed_cassettes(Path("evals/cassettes"), Path("evals"))


def test_eval_live_with_an_injected_stub_writes_a_separate_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "live-cassettes"
    report = run_live(
        Path("evals"),
        environ=_live_env(str(destination)),
        work_dir=tmp_path / "work",
        provider=FakeProvider(),
    )
    assert report.ok, report.text
    assert report.passed == report.total
    assert "model=model-under-test" in report.text
    assert "price_date=2026-01-15" in report.text
    assert "latency_us_p50=" in report.text
    assert "(llm calls only)" in report.text
    assert "(tool steps)" in report.text
    assert load_cassette(destination / "edge_human_reject.json")
    assert destination.resolve() != Path("evals/cassettes").resolve()
    err = capsys.readouterr().err
    payloads = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    assert payloads
    assert all("message" in item and "ts" in item for item in payloads)


def test_model_call_log_is_json_and_has_no_prompt(capsys: pytest.CaptureFixture[str]) -> None:
    configure("INFO")
    bill = UsageBill(
        tokens_in=10,
        tokens_out=4,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_ticks=None,
        reasoning_assumed_extra=False,
    )
    call = LiveCall(
        provider="xai",
        model="model-under-test",
        price_date="2026-10-17",
        input_micro_usd_per_million=1_000_000,
        output_micro_usd_per_million=2_000_000,
        cached_input_micro_usd_per_million=None,
        ledger=SpendLedger(1_000_000),
    )
    call.finish("run-1", 200, bill, time.perf_counter())
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["message"] == "model_call"
    assert payload["run_id"] == "run-1"
    assert payload["price_date"] == "2026-10-17"
    assert "prompt" not in payload
    assert "api_key" not in payload
