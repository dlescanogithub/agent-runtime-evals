"""Process-wide and per-run cap for hosted model calls.

The cap is one number, applied twice: once to the run, once to the process.
Crossing either one is a hard stop. The HTTP call may already have happened.
The completion is not returned, so the runner does not act on it.
"""

from __future__ import annotations

import threading

from agent_runtime.errors import ConfigError, PermanentError, SpendCapError

_guard = threading.Lock()
_process_ledger: SpendLedger | None = None


class SpendLedger:
    def __init__(self, cap_micro_usd: int) -> None:
        if cap_micro_usd <= 0:
            raise ConfigError("MAX_LIVE_SPEND_USD must be greater than zero")
        self.cap_micro_usd = cap_micro_usd
        self._lock = threading.Lock()
        self._process_micro_usd = 0
        self._run_micro_usd: dict[str, int] = {}

    def before_call(self, run_id: str) -> None:
        with self._lock:
            run_spent = self._run_micro_usd.get(run_id, 0)
            if run_spent >= self.cap_micro_usd or self._process_micro_usd >= self.cap_micro_usd:
                raise SpendCapError(
                    _cap_message(
                        "already reached before the call",
                        run_id,
                        run_spent,
                        self._process_micro_usd,
                        self.cap_micro_usd,
                    )
                )

    def charge(self, run_id: str, cost_micro_usd: int) -> None:
        if cost_micro_usd < 0:
            raise PermanentError("live model cost cannot be negative")
        with self._lock:
            run_spent = self._run_micro_usd.get(run_id, 0) + cost_micro_usd
            process_spent = self._process_micro_usd + cost_micro_usd
            self._run_micro_usd[run_id] = run_spent
            self._process_micro_usd = process_spent
            if run_spent > self.cap_micro_usd or process_spent > self.cap_micro_usd:
                raise SpendCapError(
                    _cap_message(
                        "reached",
                        run_id,
                        run_spent,
                        process_spent,
                        self.cap_micro_usd,
                    )
                )


def process_ledger(cap_micro_usd: int) -> SpendLedger:
    """One ledger for the process. A second cap in the same process is an error."""

    global _process_ledger
    with _guard:
        if _process_ledger is None:
            _process_ledger = SpendLedger(cap_micro_usd)
            return _process_ledger
        if _process_ledger.cap_micro_usd != cap_micro_usd:
            raise ConfigError(
                "MAX_LIVE_SPEND_USD cannot change after the process spend ledger "
                f"was created. This process is capped at {_process_ledger.cap_micro_usd} "
                "micro-USD."
            )
        return _process_ledger


def reset_process_spend() -> None:
    """Drop the process ledger. Tests use this. A running server should not."""

    global _process_ledger
    with _guard:
        _process_ledger = None


def live_cost_micro_usd(
    tokens_in: int,
    tokens_out: int,
    input_micro_usd_per_million: int,
    output_micro_usd_per_million: int,
) -> int:
    """Integer micro-USD. Rates are micro-USD per 1,000,000 tokens."""

    return (
        tokens_in * input_micro_usd_per_million + tokens_out * output_micro_usd_per_million
    ) // 1_000_000


def _cap_message(when: str, run_id: str, run_spent: int, process_spent: int, cap: int) -> str:
    return (
        f"live spend cap {when}: run {run_id} spent {run_spent} micro-USD, "
        f"process spent {process_spent} micro-USD, cap {cap} micro-USD "
        "(MAX_LIVE_SPEND_USD). Hard stop. This completion will not be used."
    )
