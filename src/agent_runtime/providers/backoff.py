"""Wait before retrying a hosted model call.

Exponential backoff with jitter, capped at 8 seconds. A Retry-After value
is used as the server sent it, still capped, so one 429 cannot stall the
process for minutes. The stub never calls this. Cassette replay does not
either.
"""

from __future__ import annotations

import random

BASE_S = 0.5
CAP_S = 8.0


def retry_delay_s(
    attempt: int, retry_after_s: float | None, rng: random.Random | None = None
) -> float:
    """Seconds to wait after failure number ``attempt`` (1 on the first failure)."""

    if retry_after_s is not None and retry_after_s >= 0:
        return min(CAP_S, retry_after_s)
    exponent = max(1, attempt) - 1
    slot = min(CAP_S, BASE_S * float(2**exponent))
    source = rng if rng is not None else random.Random()
    return float(slot) * float(source.uniform(0.5, 1.0))
