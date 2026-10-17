"""The agent loop.

One iteration does one thing: recover a crashed tool, run an approved tool,
park for a human, dispatch the next tool call, finish, or ask the model.
That keeps resume boring. The ledger is the cursor.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace

from agent_runtime.config import Config
from agent_runtime.errors import GateError, PermanentError, TransientError, ValidationError
from agent_runtime.gate import requires_human_gate
from agent_runtime.history import build_request
from agent_runtime.jsonutil import as_dict, as_int, as_str, dumps, loads
from agent_runtime.logging_setup import log
from agent_runtime.pricing import cost_micro_usd
from agent_runtime.providers.base import LLMProvider
from agent_runtime.store import NewStep, SQLiteStore
from agent_runtime.tools import ToolService, safe_args
from agent_runtime.trace import Tracer
from agent_runtime.types import (
    FINAL_OUTCOMES,
    Completion,
    PendingReview,
    RunOutcome,
    RunRecord,
    StepRecord,
    ToolCall,
    decode_completion,
    encode_completion,
)

logger = logging.getLogger("agent_runtime.runner")


class AgentRunner:
    def __init__(
        self,
        config: Config,
        store: SQLiteStore,
        provider: LLMProvider,
        tools: ToolService,
    ) -> None:
        self._config = config
        self._store = store
        self._provider = provider
        self._tools = tools

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def start(
        self, payload: dict[str, object], interrupt_after_steps: int | None = None
    ) -> RunOutcome:
        user_json = dumps(payload)
        run = self._store.create_run(user_json, self._config.run_budget_micro_usd)
        log(logger, logging.INFO, "run_started", run_id=run.id, provider=self._provider.name)
        return self._loop(run.id, interrupt_after_steps)

    def resume(self, run_id: str, interrupt_after_steps: int | None = None) -> RunOutcome:
        log(logger, logging.INFO, "run_resumed", run_id=run_id)
        return self._loop(run_id, interrupt_after_steps)

    def decide(self, run_id: str, step_id: str, decision: str, reason: str = "") -> None:
        """Record a human decision. Does not execute the tool. Call resume after."""

        step = self._store.get_step(step_id)
        if step.run_id != run_id:
            raise GateError("step does not belong to this run")
        if decision not in ("approve", "reject"):
            raise GateError("decision must be approve or reject")
        # A double click is a no-op. A second decision that contradicts the
        # first one is an error. Execution does not happen in this method.
        if decision == "approve" and step.status in ("approved", "succeeded"):
            log(
                logger,
                logging.INFO,
                "gate_approve_idempotent",
                run_id=run_id,
                step_id=step_id,
                status=step.status,
            )
            return
        if decision == "reject" and step.status == "rejected":
            log(logger, logging.INFO, "gate_reject_idempotent", run_id=run_id, step_id=step_id)
            return
        if step.status != "waiting_review":
            raise GateError(f"step is {step.status}, not waiting_review")
        tracer = Tracer(self._config.trace_dir, run_id)
        if decision == "approve":
            saved = self._store.save_step(replace(step, status="approved", error=None))
            tracer.emit(
                "gate_approved",
                run_id=run_id,
                step_id=saved.id,
                name=saved.name,
                **safe_args(_tool_arguments(saved)),
            )
            log(
                logger,
                logging.INFO,
                "gate_approved",
                run_id=run_id,
                step_id=step_id,
                tool=step.name,
            )
            return
        output = dumps(
            {
                "ok": False,
                "error": {
                    "code": "human_rejected",
                    "message": reason or "A reviewer rejected this action.",
                },
            }
        )
        self._store.save_step(replace(step, status="rejected", output_json=output, error=None))
        tracer.emit("gate_rejected", run_id=run_id, step_id=step.id, name=step.name)
        log(logger, logging.INFO, "gate_rejected", run_id=run_id, step_id=step_id, tool=step.name)

    def _loop(self, run_id: str, interrupt_after: int | None) -> RunOutcome:
        owner = uuid.uuid4().hex
        if not self._store.try_lock_run(run_id, owner):
            log(logger, logging.INFO, "run_already_locked", run_id=run_id)
            return self._outcome(self._store.get_run(run_id))
        try:
            return self._loop_locked(run_id, interrupt_after)
        finally:
            self._store.unlock_run(run_id, owner)

    def _loop_locked(self, run_id: str, interrupt_after: int | None) -> RunOutcome:
        baseline = len(self._store.list_steps(run_id))
        while True:
            run = self._store.get_run(run_id)
            if run.status in ("completed", "failed"):
                return self._outcome(run)
            if run.status == "interrupted":
                run = self._store.save_run(replace(run, status="running", error=None))

            if run.consecutive_failures >= self._config.circuit_breaker_threshold:
                return self._fail(run, "circuit_open")
            if run.spent_micro_usd > run.budget_micro_usd:
                return self._fail(run, "budget_exceeded")

            steps = self._store.list_steps(run_id)
            running = next(
                (step for step in steps if step.kind == "tool" and step.status == "running"), None
            )
            if running is not None:
                if not self._execute_tool(run, running):
                    return self._outcome(self._store.get_run(run_id))
                if self._hit_interrupt(run_id, baseline, interrupt_after):
                    return self._mark_interrupted(run_id)
                continue

            approved = next((step for step in steps if step.status == "approved"), None)
            if approved is not None:
                if not self._execute_tool(run, approved):
                    return self._outcome(self._store.get_run(run_id))
                if self._hit_interrupt(run_id, baseline, interrupt_after):
                    return self._mark_interrupted(run_id)
                continue

            if any(step.status == "waiting_review" for step in steps):
                parked = self._store.save_run(replace(run, status="waiting_review", error=None))
                return self._outcome(parked)

            pending = _next_tool_call(steps)
            if pending is not None:
                self._dispatch(run, pending)
                if self._hit_interrupt(run_id, baseline, interrupt_after):
                    return self._mark_interrupted(run_id)
                continue

            final_text = _final_text(steps)
            if final_text is not None:
                return self._complete_from_model(run, final_text)

            llm_turns = sum(1 for step in steps if step.kind == "llm")
            if llm_turns >= self._config.max_agent_steps:
                return self._fail(run, "max_steps")

            failed = self._llm_turn(run, steps)
            if failed is not None:
                return failed
            if self._hit_interrupt(run_id, baseline, interrupt_after):
                return self._mark_interrupted(run_id)

    def _dispatch(self, run: RunRecord, call: ToolCall) -> None:
        error = self._tools.validate(call.name, call.arguments, run.id)
        if error is not None:
            self._store.insert_step(
                NewStep(
                    run_id=run.id,
                    kind="tool",
                    name=call.name,
                    status="succeeded",
                    input_json=_tool_input(call),
                    output_json=dumps(error),
                    idempotency_key=f"{run.id}:{call.id}",
                    max_attempts=1,
                    attempt=1,
                )
            )
            log(
                logger,
                logging.INFO,
                "tool_rejected_by_validation",
                run_id=run.id,
                tool=call.name,
                code=_error_code(error),
            )
            return
        if requires_human_gate(call.name):
            step = self._store.insert_step(
                NewStep(
                    run_id=run.id,
                    kind="tool",
                    name=call.name,
                    status="waiting_review",
                    input_json=_tool_input(call),
                    idempotency_key=f"{run.id}:{call.id}",
                    max_attempts=self._config.max_step_attempts,
                )
            )
            Tracer(self._config.trace_dir, run.id).emit(
                "gate_waiting",
                run_id=run.id,
                step_id=step.id,
                name=call.name,
                **safe_args(call.arguments),
            )
            log(
                logger, logging.INFO, "gate_waiting", run_id=run.id, step_id=step.id, tool=call.name
            )
            return
        step = self._store.insert_step(
            NewStep(
                run_id=run.id,
                kind="tool",
                name=call.name,
                status="running",
                input_json=_tool_input(call),
                idempotency_key=f"{run.id}:{call.id}",
                max_attempts=self._config.max_step_attempts,
            )
        )
        self._execute_tool(run, step)

    def _execute_tool(self, run: RunRecord, step: StepRecord) -> bool:
        """Run a tool with a bound number of attempts.

        The claim is taken before the call. A second worker sees the token
        and does not execute. The attempt counter is saved before the call.
        A crash mid-call leaves the step `running`. Resume can take it only
        when the token is still null.
        """

        claimed = self._store.claim_step_execution(step.id, uuid.uuid4().hex)
        if claimed is None:
            log(
                logger,
                logging.INFO,
                "step_already_claimed",
                run_id=run.id,
                step_id=step.id,
                tool=step.name,
            )
            return False
        step = claimed
        arguments = _tool_arguments(step)
        last_error = "tool failed"
        while True:
            started = time.perf_counter_ns()
            try:
                output = self._tools.execute(step.name, arguments, run.id)
            except TransientError as exc:
                last_error = str(exc)
                log(
                    logger,
                    logging.WARNING,
                    "tool_retry",
                    run_id=run.id,
                    step_id=step.id,
                    tool=step.name,
                    attempt=step.attempt,
                )
                if step.attempt >= step.max_attempts:
                    self._record_tool_failure(run, step, last_error, started)
                    return True
                if self._config.retry_backoff_ms:
                    time.sleep(self._config.retry_backoff_ms * step.attempt / 1000)
                step = self._store.save_step(
                    replace(step, status="running", attempt=step.attempt + 1)
                )
                continue
            except PermanentError as exc:
                self._record_tool_failure(run, step, str(exc), started)
                return True
            latency_us = _elapsed_us(started)
            saved = self._store.save_step(
                replace(
                    step,
                    status="succeeded",
                    output_json=dumps(output),
                    latency_us=latency_us,
                    error=None,
                )
            )
            self._store.save_run(replace(run, consecutive_failures=0))
            Tracer(self._config.trace_dir, run.id).emit(
                "tool_finished",
                run_id=run.id,
                step_id=saved.id,
                name=saved.name,
                status="succeeded",
                latency_us=latency_us,
                code=_error_code(output) if output.get("ok") is not True else "ok",
            )
            return True

    def _record_tool_failure(
        self, run: RunRecord, step: StepRecord, message: str, started: int
    ) -> None:
        output = dumps({"ok": False, "error": {"code": "transient_exhausted", "message": message}})
        latency_us = _elapsed_us(started)
        self._store.save_step(
            replace(
                step,
                status="failed",
                output_json=output,
                error=message,
                latency_us=latency_us,
            )
        )
        self._store.save_run(replace(run, consecutive_failures=run.consecutive_failures + 1))
        Tracer(self._config.trace_dir, run.id).emit(
            "tool_finished",
            run_id=run.id,
            step_id=step.id,
            name=step.name,
            status="failed",
            latency_us=latency_us,
        )

    def _llm_turn(self, run: RunRecord, steps: list[StepRecord]) -> RunOutcome | None:
        request = build_request(run.input_json, steps, run.id)
        started = time.perf_counter_ns()
        attempt = 0
        last_error = "model call failed"
        completion: Completion | None = None
        while attempt < self._config.max_step_attempts:
            attempt += 1
            try:
                completion = self._provider.complete(request)
                break
            except TransientError as exc:
                last_error = str(exc)
                log(logger, logging.WARNING, "model_retry", run_id=run.id, attempt=attempt)
                if self._config.retry_backoff_ms and attempt < self._config.max_step_attempts:
                    time.sleep(self._config.retry_backoff_ms * attempt / 1000)
            except PermanentError as exc:
                return self._fail(run, "provider_error", str(exc))
        if completion is None:
            return self._fail(run, "provider_error", last_error)

        latency_us = _elapsed_us(started)
        # Hosted providers price the call from the operator's table and
        # already charged the live cap. The stub has no such number, so
        # the synthetic table in pricing.py still applies.
        price = (
            completion.cost_micro_usd
            if completion.cost_micro_usd is not None
            else cost_micro_usd(completion.tokens_in, completion.tokens_out)
        )
        self._store.insert_step(
            NewStep(
                run_id=run.id,
                kind="llm",
                name="completion",
                status="succeeded",
                input_json=dumps({"provider": self._provider.name}),
                output_json=encode_completion(completion),
                idempotency_key=f"{run.id}:llm:{len(steps)}",
                max_attempts=self._config.max_step_attempts,
                attempt=attempt,
                latency_us=latency_us,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
                cost_micro_usd=price,
            )
        )
        spent = run.spent_micro_usd + price
        # A successful model call does not clear tool failures. Otherwise a
        # model that keeps calling a broken tool would reset the breaker.
        self._store.save_run(replace(run, spent_micro_usd=spent))
        Tracer(self._config.trace_dir, run.id).emit(
            "llm_finished",
            run_id=run.id,
            name="completion",
            latency_us=latency_us,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            cost_micro_usd=price,
            provider=self._provider.name,
        )
        return None

    def _complete_from_model(self, run: RunRecord, content: str) -> RunOutcome:
        try:
            output = _parse_final(content)
        except ValidationError as exc:
            return self._fail(run, "invalid_final_output", str(exc))
        saved = self._store.save_run(
            replace(run, status="completed", output_json=dumps(output), error=None)
        )
        log(logger, logging.INFO, "run_completed", run_id=run.id, outcome=output.get("outcome"))
        return self._outcome(saved)

    def _fail(self, run: RunRecord, code: str, detail: str | None = None) -> RunOutcome:
        message = code if detail is None else f"{code}: {detail}"
        saved = self._store.save_run(replace(run, status="failed", error=message))
        log(logger, logging.INFO, "run_failed", run_id=run.id, error=code)
        return self._outcome(saved)

    def _mark_interrupted(self, run_id: str) -> RunOutcome:
        run = self._store.get_run(run_id)
        saved = self._store.save_run(replace(run, status="interrupted", error=None))
        log(logger, logging.INFO, "run_interrupted", run_id=run_id)
        return self._outcome(saved)

    def _hit_interrupt(self, run_id: str, baseline: int, interrupt_after: int | None) -> bool:
        if interrupt_after is None:
            return False
        return len(self._store.list_steps(run_id)) - baseline >= interrupt_after

    def _outcome(self, run: RunRecord) -> RunOutcome:
        steps = self._store.list_steps(run.id)
        pending: list[PendingReview] = []
        tokens_in = 0
        tokens_out = 0
        for step in steps:
            tokens_in += step.tokens_in
            tokens_out += step.tokens_out
            if step.status == "waiting_review":
                pending.append(
                    PendingReview(
                        step_id=step.id,
                        tool_name=step.name,
                        arguments=_tool_arguments(step),
                    )
                )
        output: dict[str, object] | None = None
        if run.output_json is not None:
            output = as_dict(loads(run.output_json))
        return RunOutcome(
            run_id=run.id,
            status=run.status,
            output=output,
            pending=tuple(pending),
            error=run.error,
            spent_micro_usd=run.spent_micro_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )


def _next_tool_call(steps: list[StepRecord]) -> ToolCall | None:
    last_llm: StepRecord | None = None
    for step in steps:
        if step.kind == "llm" and step.status == "succeeded":
            last_llm = step
    if last_llm is None or last_llm.output_json is None:
        return None
    if any(step.seq > last_llm.seq for step in steps):
        # Tools for this turn are already recorded, or a later turn exists.
        # A tool step after the llm means we only return calls that have no step.
        pass
    completion = decode_completion(last_llm.output_json)
    done = {_tool_call_id(step) for step in steps if step.kind == "tool"}
    for call in completion.tool_calls:
        if call.id not in done:
            return call
    return None


def _final_text(steps: list[StepRecord]) -> str | None:
    last_llm: StepRecord | None = None
    for step in steps:
        if step.kind == "llm" and step.status == "succeeded":
            last_llm = step
    if last_llm is None or last_llm.output_json is None:
        return None
    if any(step.seq > last_llm.seq for step in steps):
        return None
    completion = decode_completion(last_llm.output_json)
    if completion.tool_calls:
        return None
    return completion.content or ""


def _parse_final(content: str) -> dict[str, object]:
    raw = as_dict(loads(content))
    outcome = as_str(raw.get("outcome"), "outcome")
    if outcome not in FINAL_OUTCOMES:
        raise ValidationError("outcome is not a known value")
    order_id = as_str(raw.get("order_id"), "order_id")
    summary = as_str(raw.get("customer_summary"), "customer_summary")
    if not summary.strip():
        raise ValidationError("customer_summary is empty")
    amount_value = raw.get("amount_cents")
    amount: int | None
    if amount_value is None:
        amount = None
    else:
        amount = as_int(amount_value, "amount_cents")
    return {
        "amount_cents": amount,
        "customer_summary": summary,
        "order_id": order_id,
        "outcome": outcome,
    }


def _tool_input(call: ToolCall) -> str:
    return dumps({"arguments": call.arguments, "name": call.name, "tool_call_id": call.id})


def _tool_arguments(step: StepRecord) -> dict[str, object]:
    payload = as_dict(loads(step.input_json))
    return as_dict(payload.get("arguments"))


def _tool_call_id(step: StepRecord) -> str:
    payload = as_dict(loads(step.input_json))
    return as_str(payload.get("tool_call_id"), "tool_call_id")


def _error_code(envelope: dict[str, object]) -> str:
    error = envelope.get("error")
    if not isinstance(error, dict):
        return ""
    code = as_dict(error).get("code")
    return code if isinstance(code, str) else ""


def _elapsed_us(started_ns: int) -> int:
    return max(0, int((time.perf_counter_ns() - started_ns) / 1000))
