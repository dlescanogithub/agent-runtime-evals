"""Retry waits grow, stay capped, and honor Retry-After."""

import random

from agent_runtime.providers.backoff import CAP_S, retry_delay_s
from agent_runtime.providers.http import retry_after_seconds


def test_delay_doubles_then_caps() -> None:
    rng = random.Random(0)
    first = retry_delay_s(1, None, rng)
    second = retry_delay_s(2, None, random.Random(0))
    later = retry_delay_s(20, None, random.Random(0))
    assert 0.25 <= first <= 0.5
    assert 0.5 <= second <= 1.0
    assert later == CAP_S * random.Random(0).uniform(0.5, 1.0)
    assert later <= CAP_S


def test_retry_after_is_used_and_capped() -> None:
    assert retry_delay_s(1, 1.5, random.Random(0)) == 1.5
    assert retry_delay_s(1, 120, random.Random(0)) == CAP_S
    assert retry_delay_s(1, 0, random.Random(0)) == 0


def test_retry_after_header_parses_seconds() -> None:
    assert retry_after_seconds({"retry-after": "2"}) == 2
    assert retry_after_seconds({}) is None
    assert retry_after_seconds({"retry-after": "not-a-date"}) is None
