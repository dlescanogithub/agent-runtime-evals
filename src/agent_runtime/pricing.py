"""Synthetic price for the stub model.

These numbers are not a vendor price list. They exist so a run has a cost
the eval report can add up. A production table would be copied from the
provider's pricing page on the day it is measured. See docs/COST.md.
"""

MODEL_NAME = "stub-llm-v1"

# micro-USD per 1,000,000 tokens. $0.15 / 1M input, $0.60 / 1M output.
INPUT_MICRO_USD_PER_MILLION = 150_000
OUTPUT_MICRO_USD_PER_MILLION = 600_000


def cost_micro_usd(tokens_in: int, tokens_out: int) -> int:
    return (
        tokens_in * INPUT_MICRO_USD_PER_MILLION + tokens_out * OUTPUT_MICRO_USD_PER_MILLION
    ) // 1_000_000


def estimate_tokens(text: str) -> int:
    """About four characters per token. Stable, so cassettes do not drift."""

    return max(1, (len(text) + 3) // 4)
