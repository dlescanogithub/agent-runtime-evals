"""Shared bookkeeping for one hosted model call.

Logs the call as JSON. The fields are provider, model, run id, status,
tokens, cost, latency, and the price-table date. The prompt, the response
body, and the API key are not fields.
"""

from __future__ import annotations

import logging
import time

from agent_runtime.errors import PermanentError
from agent_runtime.logging_setup import log
from agent_runtime.providers.spend import SpendLedger
from agent_runtime.providers.usage import UsageBill, price_usage

_logger = logging.getLogger("agent_runtime.providers")


class LiveCall:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        price_date: str,
        input_micro_usd_per_million: int,
        output_micro_usd_per_million: int,
        cached_input_micro_usd_per_million: int | None,
        ledger: SpendLedger,
    ) -> None:
        self.provider = provider
        self.model = model
        self.price_date = price_date
        self.input_micro_usd_per_million = input_micro_usd_per_million
        self.output_micro_usd_per_million = output_micro_usd_per_million
        self.cached_input_micro_usd_per_million = cached_input_micro_usd_per_million
        self.ledger = ledger

    def begin(self, run_id: str) -> float:
        if not run_id.strip():
            raise PermanentError("a live model call requires CompletionRequest.run_id")
        self.ledger.before_call(run_id)
        return time.perf_counter()

    def finish(self, run_id: str, http_status: int, bill: UsageBill, started: float) -> int:
        cost, cost_source = price_usage(
            bill,
            self.input_micro_usd_per_million,
            self.output_micro_usd_per_million,
            self.cached_input_micro_usd_per_million,
        )
        latency_us = max(0, int((time.perf_counter() - started) * 1_000_000))
        log(
            _logger,
            logging.INFO,
            "model_call",
            provider=self.provider,
            model=self.model,
            run_id=run_id,
            http_status=http_status,
            tokens_in=bill.tokens_in,
            tokens_out=bill.tokens_out,
            cached_tokens=bill.cached_tokens,
            reasoning_tokens=bill.reasoning_tokens,
            reasoning_assumed_extra=bill.reasoning_assumed_extra,
            cost_micro_usd=cost,
            cost_source=cost_source,
            latency_us=latency_us,
            price_date=self.price_date,
        )
        self.ledger.charge(run_id, cost)
        return cost

    def fail(self, run_id: str, http_status: int | None, started: float) -> None:
        """Log a hosted call that did not return a completion. Do not charge it.

        A 429 often has no usage object. Inventing a token cost here would
        move the spend cap without a bill. The provider may still invoice it.
        """

        latency_us = max(0, int((time.perf_counter() - started) * 1_000_000))
        log(
            _logger,
            logging.WARNING,
            "model_call",
            provider=self.provider,
            model=self.model,
            run_id=run_id,
            http_status=http_status,
            latency_us=latency_us,
            price_date=self.price_date,
            failed=True,
        )
