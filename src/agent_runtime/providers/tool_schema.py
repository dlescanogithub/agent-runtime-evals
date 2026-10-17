"""JSON schemas for the four tools, shared by the hosted clients."""

from __future__ import annotations


def tool_parameters(name: str) -> tuple[dict[str, object], list[str]]:
    if name == "lookup_order":
        return {"order_id": {"type": "string"}}, ["order_id"]
    if name == "lookup_policy":
        return {"reason": {"type": "string"}}, ["reason"]
    if name == "send_refund":
        return {
            "order_id": {"type": "string"},
            "amount_cents": {"type": "integer"},
            "reason": {"type": "string"},
        }, ["order_id", "amount_cents", "reason"]
    return {
        "order_id": {"type": "string"},
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
    }, ["order_id", "to", "subject", "body"]


def parameter_object(name: str) -> dict[str, object]:
    properties, required = tool_parameters(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
