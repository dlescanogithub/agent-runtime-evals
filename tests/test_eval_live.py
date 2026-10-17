"""eval-live fails closed and never writes the committed cassettes."""

from pathlib import Path

import pytest

from agent_runtime.errors import ConfigError
from agent_runtime.evalkit.__main__ import main as eval_main
from agent_runtime.evalkit.cases import load_cassette
from agent_runtime.evalkit.suite import refuse_committed_cassettes, run_live
from agent_runtime.providers.fake import FakeProvider


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


def test_eval_live_with_an_injected_stub_writes_a_separate_directory(tmp_path: Path) -> None:
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
    assert "latency_us_p95=" in report.text
    assert load_cassette(destination / "edge_human_reject.json")
    assert destination.resolve() != Path("evals/cassettes").resolve()
