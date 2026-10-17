"""Deterministic stand-in for an LLM.

It never reads `customer_message`. Injection text cannot change its choices
because that field is not an input to the control flow. A real model can be
talked into a bad tool call, which is why the tools re-check policy and the
runtime gates side effects. This stub is the behavior the cassettes freeze.
"""

from __future__ import annotations

from agent_runtime.errors import ValidationError
from agent_runtime.jsonutil import as_dict, as_int, as_str, dumps, loads, optional_int
from agent_runtime.policy import OrderView, decide
from agent_runtime.pricing import estimate_tokens
from agent_runtime.types import Completion, CompletionRequest, Message, ToolCall

_FINAL_KEYS = ("amount_cents", "customer_summary", "order_id", "outcome")


class FakeProvider:
    name = "fake"

    def complete(self, request: CompletionRequest) -> Completion:
        user = _user_payload(request.messages)
        results = _tool_results(request.messages)
        tokens_in = _request_tokens(request)

        if user is None:
            return _final(tokens_in, "denied", "LG-0000", None, "The request could not be read.")

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
