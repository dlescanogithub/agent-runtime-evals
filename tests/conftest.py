from __future__ import annotations

from pathlib import Path

import pytest

from agent_runtime.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        llm_provider="fake",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        openai_timeout_s=5,
        database_path=tmp_path / "runtime.sqlite",
        trace_dir=tmp_path / "traces",
        evals_dir=Path("evals"),
        check_threshold=0.8,
        run_budget_micro_usd=100_000,
        max_step_attempts=3,
        circuit_breaker_threshold=3,
        max_agent_steps=8,
        retry_backoff_ms=0,
        log_level="WARNING",
        api_host="127.0.0.1",
        api_port=8080,
        api_token="local-test-token",
    )
