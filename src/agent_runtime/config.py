"""Process configuration.

Non-secret defaults live here so `make demo` works with an empty environment.
Secrets have no default. The only way to set a real model key is the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_runtime.errors import ConfigError

ProviderName = Literal["fake", "openai"]


@dataclass(frozen=True)
class Config:
    llm_provider: ProviderName
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    openai_timeout_s: float
    database_path: Path
    trace_dir: Path
    evals_dir: Path
    check_threshold: float
    run_budget_micro_usd: int
    max_step_attempts: int
    circuit_breaker_threshold: int
    max_agent_steps: int
    retry_backoff_ms: int
    log_level: str
    api_host: str
    api_port: int
    api_token: str | None

    @staticmethod
    def from_env(environ: dict[str, str] | None = None) -> Config:
        env = os.environ if environ is None else environ
        provider = _provider_name(env.get("LLM_PROVIDER", "fake"))
        api_key = env.get("OPENAI_API_KEY", "").strip() or None
        if provider == "openai" and api_key is None:
            raise ConfigError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return Config(
            llm_provider=provider,
            openai_api_key=api_key,
            openai_base_url=env.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_model=env.get("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_timeout_s=_float(env.get("OPENAI_TIMEOUT_S", "30"), "OPENAI_TIMEOUT_S"),
            database_path=Path(env.get("DATABASE_PATH", "var/runtime.sqlite")),
            trace_dir=Path(env.get("TRACE_DIR", "var/traces")),
            evals_dir=Path(env.get("EVALS_DIR", "evals")),
            check_threshold=_float(env.get("EVAL_CHECK_THRESHOLD", "0.8"), "EVAL_CHECK_THRESHOLD"),
            run_budget_micro_usd=_int(
                env.get("RUN_BUDGET_MICRO_USD", "100000"), "RUN_BUDGET_MICRO_USD"
            ),
            max_step_attempts=_int(env.get("MAX_STEP_ATTEMPTS", "3"), "MAX_STEP_ATTEMPTS"),
            circuit_breaker_threshold=_int(
                env.get("CIRCUIT_BREAKER_THRESHOLD", "3"), "CIRCUIT_BREAKER_THRESHOLD"
            ),
            max_agent_steps=_int(env.get("MAX_AGENT_STEPS", "8"), "MAX_AGENT_STEPS"),
            retry_backoff_ms=_int(env.get("RETRY_BACKOFF_MS", "0"), "RETRY_BACKOFF_MS"),
            log_level=env.get("LOG_LEVEL", "INFO"),
            api_host=env.get("API_HOST", "127.0.0.1"),
            api_port=_int(env.get("API_PORT", "8080"), "API_PORT"),
            api_token=env.get("API_TOKEN", "").strip() or None,
        )


def _provider_name(raw: str) -> ProviderName:
    if raw == "fake":
        return "fake"
    if raw == "openai":
        return "openai"
    raise ConfigError("LLM_PROVIDER must be fake or openai")


def _int(raw: str, name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _float(raw: str, name: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
