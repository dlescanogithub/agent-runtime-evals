"""Process configuration.

Non-secret defaults live here so `make demo` works with an empty environment.
Secrets have no default. A hosted model stays off unless LIVE_MODE=1, and
even then the key and the prices come only from the environment.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from agent_runtime.errors import ConfigError

ProviderName = Literal["fake", "openai", "xai", "anthropic"]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LIVE_REQUIRED = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_PRICE_DATE",
    "LLM_INPUT_USD_PER_MILLION",
    "LLM_OUTPUT_USD_PER_MILLION",
    "MAX_LIVE_SPEND_USD",
)


@dataclass(frozen=True)
class LiveSettings:
    """Operator-supplied price table and endpoint. No vendor price is baked in."""

    api_key: str
    base_url: str
    model: str
    timeout_s: float
    max_output_tokens: int
    price_date: str
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    cached_input_micro_usd_per_million: int | None
    max_spend_micro_usd: int


@dataclass(frozen=True)
class Config:
    llm_provider: ProviderName
    live: LiveSettings | None
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
        env: Mapping[str, str] = os.environ if environ is None else environ
        provider = _provider_name(env.get("LLM_PROVIDER", "fake"))
        return Config(
            llm_provider=provider,
            live=_live_settings(env, provider),
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
    if raw == "xai":
        return "xai"
    if raw == "anthropic":
        return "anthropic"
    raise ConfigError("LLM_PROVIDER must be fake, xai, openai, or anthropic")


def _live_settings(env: Mapping[str, str], provider: ProviderName) -> LiveSettings | None:
    live = env.get("LIVE_MODE", "").strip() == "1"
    if provider == "fake":
        if live:
            raise ConfigError(
                "LIVE_MODE=1 cannot be combined with LLM_PROVIDER=fake. "
                "The stub does not call a hosted model."
            )
        return None
    if not live:
        raise ConfigError(
            "A hosted provider requires LIVE_MODE=1. Live mode is off by default "
            "and is not used by CI. Set LIVE_MODE=1 only in a shell where "
            "LLM_API_KEY is loaded as a secret."
        )
    missing = [name for name in _LIVE_REQUIRED if not env.get(name, "").strip()]
    if missing:
        raise ConfigError(
            "LIVE_MODE=1 is missing "
            + ", ".join(missing)
            + ". Copy LLM_INPUT_USD_PER_MILLION and LLM_OUTPUT_USD_PER_MILLION "
            "from the provider's official pricing page, set LLM_PRICE_DATE to "
            "the date of that page, and load LLM_API_KEY from a secret store. "
            "This repo does not ship a vendor price or a key."
        )
    timeout_s = _float(env.get("LLM_TIMEOUT_S", "30"), "LLM_TIMEOUT_S")
    if timeout_s <= 0:
        raise ConfigError("LLM_TIMEOUT_S must be greater than zero")
    max_output_tokens = _int(env.get("LLM_MAX_OUTPUT_TOKENS", "1024"), "LLM_MAX_OUTPUT_TOKENS")
    if max_output_tokens <= 0:
        raise ConfigError("LLM_MAX_OUTPUT_TOKENS must be greater than zero")
    return LiveSettings(
        api_key=env["LLM_API_KEY"].strip(),
        base_url=_base_url(env["LLM_BASE_URL"]),
        model=env["LLM_MODEL"].strip(),
        timeout_s=timeout_s,
        max_output_tokens=max_output_tokens,
        price_date=_price_date(env["LLM_PRICE_DATE"]),
        input_micro_usd_per_million=_usd_to_micro(
            env["LLM_INPUT_USD_PER_MILLION"], "LLM_INPUT_USD_PER_MILLION"
        ),
        output_micro_usd_per_million=_usd_to_micro(
            env["LLM_OUTPUT_USD_PER_MILLION"], "LLM_OUTPUT_USD_PER_MILLION"
        ),
        cached_input_micro_usd_per_million=_optional_usd(
            env.get("LLM_CACHED_INPUT_USD_PER_MILLION", ""),
            "LLM_CACHED_INPUT_USD_PER_MILLION",
        ),
        max_spend_micro_usd=_usd_to_micro(env["MAX_LIVE_SPEND_USD"], "MAX_LIVE_SPEND_USD"),
    )


def _base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ConfigError("LLM_BASE_URL must be an http(s) URL with a host")
    return value


def _price_date(raw: str) -> str:
    value = raw.strip()
    if _DATE.fullmatch(value) is None:
        raise ConfigError(
            "LLM_PRICE_DATE must be YYYY-MM-DD, the date of the provider pricing page you copied"
        )
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ConfigError("LLM_PRICE_DATE is not a real calendar date") from exc
    return value


def _optional_usd(raw: str, name: str) -> int | None:
    if not raw.strip():
        return None
    return _usd_to_micro(raw, name)


def _usd_to_micro(raw: str, name: str) -> int:
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ConfigError(f"{name} must be a USD amount") from exc
    if not value.is_finite():
        raise ConfigError(f"{name} must be a USD amount")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -6:
        raise ConfigError(f"{name} has more than 6 decimal places")
    if value <= 0:
        raise ConfigError(
            f"{name} must be greater than zero. Copy it from the provider's "
            "official pricing page. A zero price would disable the spend cap."
        )
    return int(value * Decimal(1_000_000))


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
