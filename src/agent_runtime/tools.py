"""Typed tools.

Validation runs before any write and before the human gate. A call that
fails validation never reaches a reviewer and never moves money.

send_refund checks the policy again at execution time. Approval is not a
blank cheque: the order may have changed while the step was waiting.
"""

from __future__ import annotations

import re

from agent_runtime.catalog import OrderCatalog
from agent_runtime.errors import ValidationError
from agent_runtime.jsonutil import as_dict, dumps, loads
from agent_runtime.policy import MAX_REFUND_CENTS, WINDOWS_DAYS, OrderView, decide
from agent_runtime.refund_claims import (
    refund_effect_matches,
    stated_refund_cents,
    text_claims_refund_done,
)
from agent_runtime.store import SQLiteStore

ORDER_ID_RE = re.compile(r"^LG-[0-9]{4}$")
REASON_RE = re.compile(r"^[a-z_]{1,64}$")
EMAIL_RE = re.compile(r"^[a-z0-9.]+@lumen-goods\.example$")
FOREIGN_ORDER_RE = re.compile(r"LG-[0-9]{4}")

# Keys a trace line may copy. Everything else (email, body) stays in SQLite.
TRACE_SAFE_ARGS = frozenset({"order_id", "amount_cents", "reason"})


def ok(data: dict[str, object]) -> dict[str, object]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, **extra: object) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message}
    error.update(extra)
    return {"ok": False, "error": error}


def effect_key(tool_name: str, parts: dict[str, object]) -> str:
    """Business key, not the model's key.

    The model is not allowed to invent the idempotency key. Two identical
    refunds share one key, so a retry or a second run cannot pay twice.
    """

    return f"{tool_name}:{dumps(parts)}"


def safe_args(arguments: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in arguments.items() if key in TRACE_SAFE_ARGS}


class ToolService:
    def __init__(self, catalog: OrderCatalog, store: SQLiteStore) -> None:
        self._catalog = catalog
        self._store = store

    def validate(
        self, name: str, arguments: dict[str, object], run_id: str | None = None
    ) -> dict[str, object] | None:
        """Return an error envelope, or None when the call may proceed."""

        if name == "lookup_order":
            error = _validate_lookup_order(arguments)
            if error is not None:
                return error
            return self._ticket_guard(run_id, arguments)
        if name == "lookup_policy":
            return _validate_lookup_policy(arguments)
        if name == "send_refund":
            error = _validate_send_refund(arguments)
            if error is not None:
                return error
            capped = self._above_requested(run_id, arguments)
            if capped is not None:
                return capped
            return self._refund_guards(run_id, arguments)
        if name == "send_email":
            error = self._validate_send_email(arguments, run_id)
            if error is not None:
                return error
            return self._ticket_guard(run_id, arguments)
        return fail("unknown_tool", f"Unknown tool: {name}")

    def execute(
        self, name: str, arguments: dict[str, object], run_id: str | None = None
    ) -> dict[str, object]:
        if name == "lookup_order":
            guard = self._ticket_guard(run_id, arguments)
            if guard is not None:
                return guard
            return self._lookup_order(arguments)
        if name == "lookup_policy":
            return _lookup_policy(arguments)
        if name == "send_refund":
            return self._send_refund(arguments, run_id)
        if name == "send_email":
            guard = self._ticket_guard(run_id, arguments)
            if guard is not None:
                return guard
            claim = self._false_refund_email(arguments, run_id)
            if claim is not None:
                return claim
            return self._send_email(arguments)
        return fail("unknown_tool", f"Unknown tool: {name}")

    def _lookup_order(self, arguments: dict[str, object]) -> dict[str, object]:
        order_id = _require_str(arguments, "order_id")
        order = self._catalog.get(order_id)
        if order is None:
            return ok({"found": False, "order_id": order_id})
        already = self._store.refunded_cents(order_id)
        refundable = max(0, order.refundable_cents - already)
        status = "refunded" if refundable == 0 else order.status
        return ok(
            {
                "found": True,
                "order_id": order.order_id,
                "email": order.email,
                "item": order.item,
                "total_cents": order.total_cents,
                "refundable_cents": refundable,
                "days_since_delivery": order.days_since_delivery,
                "status": status,
            }
        )

    def _send_refund(self, arguments: dict[str, object], run_id: str | None) -> dict[str, object]:
        order_id = _require_str(arguments, "order_id")
        amount = _require_int(arguments, "amount_cents")
        reason = _require_str(arguments, "reason")
        key = effect_key(
            "send_refund",
            {"order_id": order_id, "amount_cents": amount, "reason": reason},
        )
        # A retry must return the original receipt. Checking the policy first
        # would see the balance already reduced and would look like a denial.
        existing = self._store.get_effect(key)
        if existing is not None:
            return existing
        blocked = self._refund_guards(run_id, arguments)
        if blocked is not None:
            return blocked
        capped = self._above_requested(run_id, arguments)
        if capped is not None:
            return capped
        order = self._catalog.get(order_id)
        if order is None:
            return fail("not_found", "No order exists with that id.")
        already = self._store.refunded_cents(order_id)
        view = OrderView(
            refundable_cents=max(0, order.refundable_cents - already),
            days_since_delivery=order.days_since_delivery,
        )
        decision = decide(view, reason, amount)
        # The caller must pass the exact policy amount. We do not silently
        # lower it at execution time, or the reviewer would have approved a
        # different number than the one that moves.
        if not decision.allowed or decision.amount_cents != amount:
            code = decision.code if not decision.allowed else "amount_mismatch"
            return fail("policy_denied", decision.message, policy_code=code)
        output = ok(
            {
                "status": "executed",
                "order_id": order_id,
                "amount_cents": amount,
                "reason": reason,
                "idempotency_key": key,
            }
        )
        return self._store.commit_effect(key, "send_refund", output, order_id, amount)

    def _send_email(self, arguments: dict[str, object]) -> dict[str, object]:
        order_id = _require_str(arguments, "order_id")
        to = _require_str(arguments, "to")
        subject = _require_str(arguments, "subject")
        # Body was validated before the gate. Re-read it so a direct execute
        # still fails closed if the argument is missing.
        _require_str(arguments, "body")
        order = self._catalog.get(order_id)
        if order is None:
            return fail("not_found", "No order exists with that id.")
        if to != order.email:
            return fail(
                "email_not_on_order",
                "The recipient is not the email address on the order.",
            )
        key = effect_key("send_email", {"order_id": order_id, "to": to, "subject": subject})
        existing = self._store.get_effect(key)
        if existing is not None:
            return existing
        output = ok(
            {
                "status": "executed",
                "order_id": order_id,
                "to": to,
                "subject": subject,
                "idempotency_key": key,
            }
        )
        # No ledger change. The effect row is the record that we would have sent.
        return self._store.commit_effect(key, "send_email", output, None, None)

    def _false_refund_email(
        self, arguments: dict[str, object], run_id: str | None
    ) -> dict[str, object] | None:
        """Block an email that says a refund happened when it did not."""

        subject = arguments.get("subject")
        body = arguments.get("body")
        text = " ".join(part for part in (subject, body) if isinstance(part, str))
        if not text_claims_refund_done(text):
            return None
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or run_id is None:
            return fail(
                "false_refund_claim",
                "The email says a refund was processed or issued, and no executed "
                "send_refund matches this order and amount.",
            )
        amount = stated_refund_cents(text)
        steps = self._store.list_steps(run_id)
        if refund_effect_matches(steps, order_id, amount):
            return None
        return fail(
            "false_refund_claim",
            "The email says a refund was processed or issued, and no executed "
            "send_refund matches this order and amount.",
        )

    def _validate_send_email(
        self, arguments: dict[str, object], run_id: str | None
    ) -> dict[str, object] | None:
        order_id = arguments.get("order_id")
        to = arguments.get("to")
        subject = arguments.get("subject")
        body = arguments.get("body")
        if not isinstance(order_id, str) or ORDER_ID_RE.fullmatch(order_id) is None:
            return fail(
                "invalid_order_id",
                "order_id must be LG- and four digits, for example LG-0001.",
            )
        if not isinstance(to, str) or EMAIL_RE.fullmatch(to) is None:
            return fail(
                "invalid_email",
                "Email must be a synthetic lumen-goods.example address.",
            )
        if not isinstance(subject, str) or not 1 <= len(subject) <= 120:
            return fail("invalid_subject", "Subject must be 1 to 120 characters.")
        if not isinstance(body, str) or not 1 <= len(body) <= 500:
            return fail("invalid_body", "Body must be 1 to 500 characters.")
        leaked = [match for match in FOREIGN_ORDER_RE.findall(body) if match != order_id]
        if leaked:
            return fail("foreign_order_in_body", "The email body mentions another order.")
        claim = self._false_refund_email(arguments, run_id)
        if claim is not None:
            return claim
        order = self._catalog.get(order_id)
        if order is not None and to != order.email:
            # Do not ask a reviewer to approve an email to the wrong person.
            return fail(
                "email_not_on_order",
                "The recipient is not the email address on the order.",
            )
        return None

    def _ticket_order_id(self, run_id: str) -> str | None:
        raw = as_dict(loads(self._store.get_run(run_id).input_json))
        order_id = raw.get("order_id")
        if isinstance(order_id, str):
            return order_id
        return None

    def _ticket_guard(
        self, run_id: str | None, arguments: dict[str, object]
    ) -> dict[str, object] | None:
        """The model may only touch the order on the request, not one it invents."""

        if run_id is None:
            return None
        ticket = self._ticket_order_id(run_id)
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or ticket is None:
            return None
        if order_id != ticket:
            return fail(
                "order_not_on_ticket",
                "Tools can only touch the order id on this run.",
            )
        return None

    def _above_requested(
        self, run_id: str | None, arguments: dict[str, object]
    ) -> dict[str, object] | None:
        """The model may not refund more than the customer asked for.

        When the request does not state a positive amount, only the order
        balance and the hard cap apply. Those stay in policy.decide.
        """

        if run_id is None:
            return None
        amount = arguments.get("amount_cents")
        if isinstance(amount, bool) or not isinstance(amount, int):
            return None
        raw = as_dict(loads(self._store.get_run(run_id).input_json))
        requested = raw.get("requested_amount_cents")
        if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
            return None
        if amount > requested:
            return fail(
                "above_requested",
                "amount_cents is above the amount the customer requested.",
            )
        return None

    def _refund_guards(
        self, run_id: str | None, arguments: dict[str, object]
    ) -> dict[str, object] | None:
        ticket_error = self._ticket_guard(run_id, arguments)
        if ticket_error is not None:
            return ticket_error
        if run_id is None:
            return None
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str):
            return None
        if not self._lookups_done(run_id, order_id):
            return fail(
                "lookup_required",
                "send_refund requires lookup_order and lookup_policy in this run.",
            )
        return None

    def _lookups_done(self, run_id: str, order_id: str) -> bool:
        saw_order = False
        saw_policy = False
        for step in self._store.list_steps(run_id):
            if step.kind != "tool" or step.status != "succeeded" or not step.output_json:
                continue
            try:
                payload = as_dict(loads(step.output_json))
            except ValidationError:
                continue
            if payload.get("ok") is not True:
                continue
            if step.name == "lookup_order":
                data_raw = payload.get("data")
                if isinstance(data_raw, dict):
                    data = as_dict(data_raw)
                    if data.get("order_id") == order_id and data.get("found") is True:
                        saw_order = True
            if step.name == "lookup_policy" and isinstance(payload.get("data"), dict):
                saw_policy = True
        return saw_order and saw_policy


def _validate_lookup_order(arguments: dict[str, object]) -> dict[str, object] | None:
    order_id = arguments.get("order_id")
    if not isinstance(order_id, str) or ORDER_ID_RE.fullmatch(order_id) is None:
        return fail(
            "invalid_order_id",
            "order_id must be LG- and four digits, for example LG-0001.",
        )
    return None


def _validate_lookup_policy(arguments: dict[str, object]) -> dict[str, object] | None:
    reason = arguments.get("reason")
    if not isinstance(reason, str) or REASON_RE.fullmatch(reason) is None:
        return fail("invalid_reason", "reason must be a short snake_case string.")
    return None


def _validate_send_refund(arguments: dict[str, object]) -> dict[str, object] | None:
    order_id = arguments.get("order_id")
    amount = arguments.get("amount_cents")
    reason = arguments.get("reason")
    if not isinstance(order_id, str) or ORDER_ID_RE.fullmatch(order_id) is None:
        return fail(
            "invalid_order_id",
            "order_id must be LG- and four digits, for example LG-0001.",
        )
    if isinstance(amount, bool) or not isinstance(amount, int):
        return fail("invalid_amount", "amount_cents must be an integer.")
    # Zero and negative amounts are refused here, before the human gate.
    # policy.decide refuses them again if execute is called directly.
    if not 1 <= amount <= MAX_REFUND_CENTS:
        return fail("invalid_amount", f"amount_cents must be between 1 and {MAX_REFUND_CENTS}.")
    if not isinstance(reason, str) or REASON_RE.fullmatch(reason) is None:
        return fail("invalid_reason", "reason must be a short snake_case string.")
    return None


def _lookup_policy(arguments: dict[str, object]) -> dict[str, object]:
    reason = _require_str(arguments, "reason")
    window = WINDOWS_DAYS.get(reason)
    return ok(
        {
            "reason": reason,
            "known": window is not None,
            "window_days": window,
            "known_reasons": sorted(WINDOWS_DAYS),
        }
    )


def _require_str(arguments: dict[str, object], field: str) -> str:
    value = arguments.get(field)
    if not isinstance(value, str):
        raise RuntimeError(f"{field} should have been validated")
    return value


def _require_int(arguments: dict[str, object], field: str) -> int:
    value = arguments.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{field} should have been validated")
    return value
