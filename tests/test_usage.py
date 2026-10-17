"""Usage bills from fake payloads. No network."""

from agent_runtime.providers.usage import (
    bill_from_anthropic_usage,
    bill_from_openai_usage,
    price_usage,
)


def test_reasoning_tokens_outside_completion_are_counted_once() -> None:
    bill = bill_from_openai_usage(
        {
            "prompt_tokens": 205,
            "completion_tokens": 1,
            "total_tokens": 396,
            "completion_tokens_details": {"reasoning_tokens": 190},
        }
    )
    assert bill.tokens_out == 191
    assert bill.reasoning_tokens == 190
    assert bill.reasoning_assumed_extra is False


def test_reasoning_without_total_is_added_and_marked() -> None:
    bill = bill_from_openai_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 1,
            "completion_tokens_details": {"reasoning_tokens": 4},
        }
    )
    assert bill.tokens_out == 5
    assert bill.reasoning_assumed_extra is True


def test_cost_ticks_replace_the_token_table() -> None:
    bill = bill_from_openai_usage(
        {
            "prompt_tokens": 205,
            "completion_tokens": 1,
            "total_tokens": 396,
            "completion_tokens_details": {"reasoning_tokens": 190},
            "cost_in_usd_ticks": 1_140_000,
        }
    )
    cost, source = price_usage(bill, 1_250_000, 2_500_000, 200_000)
    assert source == "cost_in_usd_ticks"
    assert cost == 114


def test_cached_tokens_use_the_cached_rate_when_it_is_set() -> None:
    bill = bill_from_openai_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_tokens_details": {"cached_tokens": 80},
        }
    )
    cost, source = price_usage(bill, 1_000_000, 2_000_000, 200_000)
    assert bill.cached_tokens == 80
    assert source == "token_table"
    assert cost == 56


def test_cached_tokens_without_a_cached_price_are_not_silent() -> None:
    bill = bill_from_openai_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "cached_tokens": 80,
        }
    )
    cost, source = price_usage(bill, 1_000_000, 2_000_000, None)
    assert source == "token_table_cached_as_uncached"
    assert cost == 120


def test_anthropic_cache_read_is_split_from_fresh_input() -> None:
    bill = bill_from_anthropic_usage(
        {"input_tokens": 20, "output_tokens": 10, "cache_read_input_tokens": 80}
    )
    assert bill.tokens_in == 100
    assert bill.cached_tokens == 80
    cost, source = price_usage(bill, 1_000_000, 2_000_000, 200_000)
    assert source == "token_table"
    assert cost == 56
