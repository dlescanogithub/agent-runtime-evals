"""Refund rules. Pure function: same inputs, same decision, no I/O.

The stub model and the send_refund tool both call `decide`. The model is not
trusted to do the arithmetic. If the two ever disagreed, the tool would refuse
to move money.
"""

from __future__ import annotations

from dataclasses import dataclass

# Days after delivery. changed_mind is shorter on purpose.
WINDOWS_DAYS: dict[str, int] = {
    "damaged": 30,
    "late": 30,
    "duplicate_charge": 30,
    "not_as_described": 30,
    "changed_mind": 14,
}

# Hard ceiling on a single refund call, separate from the order balance.
MAX_REFUND_CENTS = 100_000


@dataclass(frozen=True)
class OrderView:
    refundable_cents: int
    days_since_delivery: int


@dataclass(frozen=True)
class Decision:
    allowed: bool
    amount_cents: int | None
    code: str
    message: str


def decide(order: OrderView | None, reason: str, requested_amount_cents: int) -> Decision:
    if order is None:
        return Decision(False, None, "not_found", "No order exists with that id.")
    if requested_amount_cents <= 0:
        return Decision(False, None, "zero_amount", "The refund amount must be greater than zero.")
    window = WINDOWS_DAYS.get(reason)
    if window is None:
        known = ", ".join(sorted(WINDOWS_DAYS))
        return Decision(False, None, "unknown_reason", f"Unknown reason. Known reasons: {known}.")
    if order.days_since_delivery > window:
        return Decision(
            False,
            None,
            "outside_window",
            f"The {reason} window is {window} days and this order is older.",
        )
    if order.refundable_cents <= 0:
        return Decision(False, None, "already_refunded", "This order has no refundable balance.")
    amount = min(requested_amount_cents, order.refundable_cents, MAX_REFUND_CENTS)
    if amount <= 0:
        return Decision(False, None, "already_refunded", "This order has no refundable balance.")
    return Decision(True, amount, "ok", "The refund is inside policy.")
