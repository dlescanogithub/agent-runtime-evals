"""Token counts and a cost estimate from a hosted usage object.

xAI leaves reasoning tokens out of ``completion_tokens`` and also sends
``total_tokens``. Output tokens are ``max(completion_tokens, total_tokens -
prompt_tokens)`` when ``total_tokens`` is present, so those reasoning tokens
are counted once. A provider that already folds reasoning into
``completion_tokens`` is not double-counted, because ``total_tokens -
prompt_tokens`` matches ``completion_tokens``.

If ``total_tokens`` is missing and ``reasoning_tokens`` is present, the
reasoning tokens are added and ``reasoning_assumed_extra`` is true. The log
says so. That matches the xAI shape. It would double-count a provider that
already included them and omitted ``total_tokens``.

``usage.cost_in_usd_ticks`` is the provider's own bill (1 tick = 1e-10 USD).
When it is present the spend cap uses it, rounded up to the next micro-USD,
and the token price table is not applied. That bill already includes
reasoning and any cache discount.

Cached input (``prompt_tokens_details.cached_tokens``, or Anthropic
``cache_read_input_tokens``) uses ``LLM_CACHED_INPUT_USD_PER_MILLION`` when
that variable is set. When it is not set, and the API did not send cost
ticks, cached tokens are priced at the full input rate and the cost source
is ``token_table_cached_as_uncached``. That is an upper bound, and it is
written on the log. It is not a silent over-estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.errors import PermanentError
from agent_runtime.jsonutil import as_dict, as_int

_TICKS_PER_MICRO_USD = 10_000


@dataclass(frozen=True)
class UsageBill:
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    reasoning_tokens: int
    cost_ticks: int | None
    reasoning_assumed_extra: bool


def bill_from_openai_usage(usage: dict[str, object]) -> UsageBill:
    prompt = as_int(usage.get("prompt_tokens"), "prompt_tokens")
    completion = as_int(usage.get("completion_tokens"), "completion_tokens")
    reasoning = _optional_int(
        _nested(usage, "completion_tokens_details", "reasoning_tokens"),
        "reasoning_tokens",
    )
    total = _optional_int(usage.get("total_tokens"), "total_tokens")
    assumed = False
    if total is None:
        tokens_out = completion + (reasoning or 0)
        assumed = reasoning is not None and reasoning > 0
    else:
        tokens_out = max(completion, total - prompt)
    cached = _cached_tokens(usage)
    if cached > prompt:
        cached = prompt
    return UsageBill(
        tokens_in=prompt,
        tokens_out=max(0, tokens_out),
        cached_tokens=cached,
        reasoning_tokens=0 if reasoning is None else reasoning,
        cost_ticks=_optional_int(usage.get("cost_in_usd_ticks"), "cost_in_usd_ticks"),
        reasoning_assumed_extra=assumed,
    )


def bill_from_anthropic_usage(usage: dict[str, object]) -> UsageBill:
    """Messages API counts. Cache reads and writes are separate from input_tokens."""

    fresh = as_int(usage.get("input_tokens"), "input_tokens")
    output = as_int(usage.get("output_tokens"), "output_tokens")
    cache_read = _optional_int(usage.get("cache_read_input_tokens"), "cache_read_input_tokens") or 0
    cache_write = (
        _optional_int(usage.get("cache_creation_input_tokens"), "cache_creation_input_tokens") or 0
    )
    return UsageBill(
        tokens_in=fresh + cache_read + cache_write,
        tokens_out=output,
        cached_tokens=cache_read,
        reasoning_tokens=0,
        cost_ticks=_optional_int(usage.get("cost_in_usd_ticks"), "cost_in_usd_ticks"),
        reasoning_assumed_extra=False,
    )


def price_usage(
    bill: UsageBill,
    input_micro_usd_per_million: int,
    output_micro_usd_per_million: int,
    cached_input_micro_usd_per_million: int | None,
) -> tuple[int, str]:
    if bill.cost_ticks is not None:
        if bill.cost_ticks < 0:
            raise PermanentError("cost_in_usd_ticks cannot be negative")
        # Round up so a fraction of a micro-USD still counts against the cap.
        return (bill.cost_ticks + _TICKS_PER_MICRO_USD - 1) // _TICKS_PER_MICRO_USD, (
            "cost_in_usd_ticks"
        )
    cached = min(bill.cached_tokens, bill.tokens_in)
    if cached > 0 and cached_input_micro_usd_per_million is None:
        cost = _token_cost(
            bill.tokens_in,
            bill.tokens_out,
            input_micro_usd_per_million,
            output_micro_usd_per_million,
            0,
            input_micro_usd_per_million,
        )
        return cost, "token_table_cached_as_uncached"
    cached_rate = (
        input_micro_usd_per_million
        if cached_input_micro_usd_per_million is None
        else cached_input_micro_usd_per_million
    )
    return (
        _token_cost(
            bill.tokens_in,
            bill.tokens_out,
            input_micro_usd_per_million,
            output_micro_usd_per_million,
            cached,
            cached_rate,
        ),
        "token_table",
    )


def _token_cost(
    tokens_in: int,
    tokens_out: int,
    input_rate: int,
    output_rate: int,
    cached: int,
    cached_rate: int,
) -> int:
    uncached = tokens_in - cached
    return (uncached * input_rate + cached * cached_rate + tokens_out * output_rate) // 1_000_000


def _cached_tokens(usage: dict[str, object]) -> int:
    detailed = _nested(usage, "prompt_tokens_details", "cached_tokens")
    if detailed is not None:
        return _optional_int(detailed, "cached_tokens") or 0
    return _optional_int(usage.get("cached_tokens"), "cached_tokens") or 0


def _nested(usage: dict[str, object], group: str, field: str) -> object:
    raw = usage.get(group)
    if not isinstance(raw, dict):
        return None
    return as_dict(raw).get(field)


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return as_int(value, field)
