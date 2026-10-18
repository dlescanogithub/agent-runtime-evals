"""The agent loop.

One iteration does one thing: recover a crashed tool, run an approved tool,
park for a human, dispatch the next tool call, finish, or ask the model.
That keeps resume boring. The ledger is the cursor.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, replace

from agent_runtime.config import Config
from agent_runtime.errors import GateError, PermanentError, TransientError, ValidationError
from agent_runtime.gate import requires_human_gate
from agent_runtime.history import build_request
from agent_runtime.jsonutil import as_dict, as_int, as_str, dumps, loads
from agent_runtime.logging_setup import log
from agent_runtime.pricing import cost_micro_usd
from agent_runtime.providers.backoff import retry_delay_s
from agent_runtime.providers.base import LLMProvider
from agent_runtime.refund_claims import (
    refund_effect_matches,
    stated_refund_cents,
    text_claims_refund_done,
)
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
                finished = self._complete_from_model(run, final_text)
                if finished is not None:
                    return finished
                continue

            # A nudge is a step. It spends the same budget as a model turn
            # so a correction cannot run for free.
            accounted = sum(1 for step in steps if step.kind in ("llm", "nudge"))
            if accounted >= self._config.max_agent_steps:
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
                log(
                    logger,
                    logging.WARNING,
                    "model_retry",
                    run_id=run.id,
                    attempt=attempt,
                    http_status=exc.http_status,
                    retry_after_s=exc.retry_after_s,
                )
                if attempt < self._config.max_step_attempts:
                    _sleep(retry_delay_s(attempt, exc.retry_after_s))
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

    def _complete_from_model(self, run: RunRecord, content: str) -> RunOutcome | None:
        try:
            output = _parse_final(content)
        except ValidationError as exc:
            return self._fail(run, "invalid_final_output", str(exc))
        # A model can say the refund happened without calling send_refund,
        # including inside an email the final outcome does not mention.
        # That must not close the run as completed. Under the cap we hand
        # the missing step back and keep going. We never insert the write.
        steps = self._store.list_steps(run.id)
        blocked = _completion_block(steps, output)
        if blocked is not None:
            # A nudge is only for an unrejected refund_completed claim.
            # needs_ops, denied, refund_rejected, and a gate rejection close
            # without asking the model to try the write again.
            if blocked.nudge and self._can_nudge(steps):
                self._record_nudge(run, output, blocked.reason)
                return None
            saved = self._store.save_run(
                replace(run, status="failed", output_json=dumps(output), error=blocked.error)
            )
            log(logger, logging.INFO, "run_needs_review", run_id=run.id, error="needs_review")
            return self._outcome(saved)
        saved = self._store.save_run(
            replace(run, status="completed", output_json=dumps(output), error=None)
        )
        log(logger, logging.INFO, "run_completed", run_id=run.id, outcome=output.get("outcome"))
        return self._outcome(saved)

    def _can_nudge(self, steps: list[StepRecord]) -> bool:
        nudges = sum(1 for step in steps if step.kind == "nudge")
        if nudges >= self._config.max_completion_nudges:
            return False
        # The nudge itself counts, and one more model turn has to fit after it.
        accounted = sum(1 for step in steps if step.kind in ("llm", "nudge"))
        return accounted + 1 < self._config.max_agent_steps

    def _record_nudge(self, run: RunRecord, output: dict[str, object], reason: str) -> None:
        index = sum(1 for step in self._store.list_steps(run.id) if step.kind == "nudge") + 1
        payload = {
            "instruction": _nudge_instruction(reason),
            "max_nudges": self._config.max_completion_nudges,
            "nudge": index,
            "order_id": output.get("order_id"),
            "outcome": output.get("outcome"),
            "reason": reason,
            "type": "completion_nudge",
        }
        self._store.insert_step(
            NewStep(
                run_id=run.id,
                kind="nudge",
                name="completion_nudge",
                status="succeeded",
                input_json=dumps({"reason": reason, "refused_outcome": output.get("outcome")}),
                output_json=dumps(payload),
                idempotency_key=f"{run.id}:nudge:{index}",
                max_attempts=1,
                attempt=1,
            )
        )
        # No order id, summary, or email body. The model-facing JSON has those.
        log(
            logger,
            logging.INFO,
            "completion_nudge",
            run_id=run.id,
            reason=reason,
            nudge=index,
            outcome=output.get("outcome"),
        )

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


@dataclass(frozen=True)
class _BlockedFinish:
    error: str
    reason: str
    nudge: bool


def _completion_block(steps: list[StepRecord], output: dict[str, object]) -> _BlockedFinish | None:
    """Refuse a false completion. Nudge only the narrow refund_completed case.

    denied, needs_ops, refund_rejected, and any other non-refund outcome
    are accepted unless the customer text claims a refund that did not
    happen. A human rejection of send_refund or send_email for this order
    is also not a nudge: asking again loops on the same gate.
    """

    if output.get("outcome") != "refund_completed":
        text_error = _customer_text_claim_error(steps, output)
        if text_error is not None:
            return _BlockedFinish(text_error, "false_refund_claim", nudge=False)
        return None
    if _human_rejected_effect(steps, output.get("order_id")):
        refund_error = _refund_claim_error(steps, output)
        if refund_error is not None:
            return _BlockedFinish(refund_error, "missing_send_refund", nudge=False)
        text_error = _customer_text_claim_error(steps, output)
        if text_error is not None:
            return _BlockedFinish(text_error, "false_refund_claim", nudge=False)
        return None
    refund_error = _refund_claim_error(steps, output)
    if refund_error is not None:
        return _BlockedFinish(refund_error, "missing_send_refund", nudge=True)
    text_error = _customer_text_claim_error(steps, output)
    if text_error is not None:
        return _BlockedFinish(text_error, "false_refund_claim", nudge=False)
    return None


def _human_rejected_effect(steps: list[StepRecord], order_id: object) -> bool:
    """True when a person already rejected a write for this order."""

    for step in steps:
        if step.status != "rejected" or step.name not in ("send_refund", "send_email"):
            continue
        if not isinstance(order_id, str):
            return True
        try:
            wrapper = as_dict(loads(step.input_json))
            arguments = as_dict(wrapper.get("arguments"))
        except ValidationError:
            return True
        if arguments.get("order_id") == order_id:
            return True
    return False


def _refund_claim_error(steps: list[StepRecord], output: dict[str, object]) -> str | None:
    """refund_completed is allowed only when that refund effect executed."""

    if output.get("outcome") != "refund_completed":
        return None
    return _missing_refund_message(steps, output, "refund_completed")


def _missing_refund_message(
    steps: list[StepRecord], output: dict[str, object], outcome_name: str
) -> str | None:
    message = (
        f"needs_review: outcome {outcome_name} but no executed send_refund "
        "effect matches this order and amount"
    )
    order_id = output.get("order_id")
    amount = output.get("amount_cents")
    if not isinstance(order_id, str) or not isinstance(amount, int) or isinstance(amount, bool):
        return message
    for step in steps:
        if step.kind != "tool" or step.name != "send_refund" or step.output_json is None:
            continue
        try:
            payload = as_dict(loads(step.output_json))
            wrapper = as_dict(loads(step.input_json))
            arguments = as_dict(wrapper.get("arguments"))
        except ValidationError:
            continue
        if payload.get("ok") is not True:
            continue
        if arguments.get("order_id") == order_id and arguments.get("amount_cents") == amount:
            return None
    return message


def _nudge_instruction(reason: str) -> str:
    if reason == "false_refund_claim":
        observed = (
            "The customer summary or an email says a refund was processed or "
            "issued, and no confirmed send_refund matches."
        )
    else:
        observed = "The outcome says the refund is completed, and no confirmed send_refund matches."
    return (
        f"{observed} That is inconsistent. The runtime will not create the write. "
        "Two finishes are valid: propose the write this ticket and the policy allow, "
        "or correct the outcome to denied or needs_ops when a refund is not warranted. "
        "Do not claim the refund is completed until a confirmed write exists."
    )


def _customer_text_claim_error(steps: list[StepRecord], output: dict[str, object]) -> str | None:
    """A summary or a sent email must not announce a refund that did not execute."""

    texts: list[tuple[str, str]] = []
    summary = output.get("customer_summary")
    order_id = output.get("order_id")
    if isinstance(summary, str) and isinstance(order_id, str):
        texts.append((order_id, summary))
    for step in steps:
        if step.kind != "tool" or step.name != "send_email" or step.output_json is None:
            continue
        try:
            payload = as_dict(loads(step.output_json))
            wrapper = as_dict(loads(step.input_json))
            arguments = as_dict(wrapper.get("arguments"))
        except ValidationError:
            continue
        if payload.get("ok") is not True:
            continue
        sent_order = arguments.get("order_id")
        if not isinstance(sent_order, str):
            continue
        subject = arguments.get("subject")
        body = arguments.get("body")
        text = " ".join(part for part in (subject, body) if isinstance(part, str))
        texts.append((sent_order, text))
    message = (
        "needs_review: customer was told a refund was processed or issued "
        "but no executed send_refund matches this order and amount"
    )
    for claimed_order, text in texts:
        if not text_claims_refund_done(text):
            continue
        if not refund_effect_matches(steps, claimed_order, stated_refund_cents(text)):
            return message
    return None


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


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
