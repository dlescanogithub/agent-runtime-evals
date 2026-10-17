from pathlib import Path

import pytest

from agent_runtime.config import Config
from agent_runtime.errors import ConfigError
from agent_runtime.secretscan import scan_repo, scan_text


def _live(provider: str = "xai", **overrides: str) -> dict[str, str]:
    env = {
        "LLM_PROVIDER": provider,
        "LIVE_MODE": "1",
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.test/v1",
        "LLM_MODEL": "model-under-test",
        "LLM_PRICE_DATE": "2026-01-15",
        "LLM_INPUT_USD_PER_MILLION": "1.50",
        "LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MAX_LIVE_SPEND_USD": "0.500000",
    }
    env.update(overrides)
    return env


def test_default_environment_is_the_stub() -> None:
    config = Config.from_env({})
    assert config.llm_provider == "fake"
    assert config.live is None


def test_hosted_provider_without_opt_in_is_rejected() -> None:
    with pytest.raises(ConfigError, match="LIVE_MODE=1"):
        Config.from_env({"LLM_PROVIDER": "xai"})
    with pytest.raises(ConfigError, match="LIVE_MODE=1"):
        Config.from_env({"LLM_PROVIDER": "openai", "LIVE_MODE": "true"})
    with pytest.raises(ConfigError, match="LIVE_MODE=1"):
        Config.from_env({"LLM_PROVIDER": "anthropic", "LIVE_MODE": "0"})


def test_fake_provider_rejects_live_mode() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER=fake"):
        Config.from_env({"LLM_PROVIDER": "fake", "LIVE_MODE": "1"})


def test_live_mode_requires_a_price_table_and_does_not_echo_the_key() -> None:
    missing = _live()
    del missing["LLM_INPUT_USD_PER_MILLION"]
    with pytest.raises(ConfigError, match="official pricing page") as exc:
        Config.from_env(missing)
    assert "test-key" not in str(exc.value)
    with pytest.raises(ConfigError, match="greater than zero"):
        Config.from_env(_live(LLM_OUTPUT_USD_PER_MILLION="0"))
    with pytest.raises(ConfigError, match="6 decimal places"):
        Config.from_env(_live(LLM_INPUT_USD_PER_MILLION="1.0000001"))
    with pytest.raises(ConfigError, match="YYYY-MM-DD"):
        Config.from_env(_live(LLM_PRICE_DATE="15-01-2026"))
    with pytest.raises(ConfigError, match="calendar date"):
        Config.from_env(_live(LLM_PRICE_DATE="2026-02-31"))
    with pytest.raises(ConfigError, match="LLM_BASE_URL"):
        Config.from_env(_live(LLM_BASE_URL="api.x.ai/v1"))
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        Config.from_env({"LLM_PROVIDER": "grok"})
    with pytest.raises(ConfigError, match="LLM_TIMEOUT_S"):
        Config.from_env(_live(LLM_TIMEOUT_S="0"))
    with pytest.raises(ConfigError, match="LLM_MAX_OUTPUT_TOKENS"):
        Config.from_env(_live(LLM_MAX_OUTPUT_TOKENS="0"))
    with pytest.raises(ConfigError, match="USD amount"):
        Config.from_env(_live(MAX_LIVE_SPEND_USD="many"))
    with pytest.raises(ConfigError, match="USD amount"):
        Config.from_env(_live(LLM_INPUT_USD_PER_MILLION="Infinity"))
    with pytest.raises(ConfigError, match="integer"):
        Config.from_env(_live(LLM_MAX_OUTPUT_TOKENS="nope"))
    with pytest.raises(ConfigError, match="number"):
        Config.from_env(_live(LLM_TIMEOUT_S="nope"))


def test_live_mode_converts_operator_prices_to_micro_usd() -> None:
    config = Config.from_env(_live())
    assert config.live is not None
    assert config.live.input_micro_usd_per_million == 1_500_000
    assert config.live.output_micro_usd_per_million == 2_000_000
    assert config.live.max_spend_micro_usd == 500_000
    assert config.live.price_date == "2026-01-15"
    assert config.live.api_key == "test-key"
    assert config.live.max_output_tokens == 1024


def test_secret_scanner_flags_a_sample_and_the_repo_is_clean() -> None:
    sample = "sk-" + ("a" * 24)
    assert "openai_key" in scan_text(sample)
    assert scan_repo(Path(".")) == []


def test_ci_workflow_does_not_enable_live_mode() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "LIVE_MODE=1" not in text
    assert "LLM_API_KEY" not in text
