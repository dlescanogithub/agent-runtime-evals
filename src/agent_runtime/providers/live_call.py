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
from agent_runtime.providers.spend import SpendLedger, live_cost_micro_usd

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
        ledger: SpendLedger,
    ) -> None:
        self.provider = provider
        self.model = model
        self.price_date = price_date
        self.input_micro_usd_per_million = input_micro_usd_per_million
        self.output_micro_usd_per_million = output_micro_usd_per_million
        self.ledger = ledger

    def begin(self, run_id: str) -> float:
        if not run_id.strip():
            raise PermanentError("a live model call requires CompletionRequest.run_id")
        self.ledger.before_call(run_id)
        return time.perf_counter()

    def finish(
        self,
        run_id: str,
        http_status: int,
        tokens_in: int,
        tokens_out: int,
        started: float,
    ) -> int:
        cost = live_cost_micro_usd(
            tokens_in,
            tokens_out,
            self.input_micro_usd_per_million,
            self.output_micro_usd_per_million,
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
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_micro_usd=cost,
            latency_us=latency_us,
            price_date=self.price_date,
        )
        self.ledger.charge(run_id, cost)
        return cost
