from agent_runtime.policy import OrderView, decide


def test_caps_amount_to_the_refundable_balance() -> None:
    decision = decide(OrderView(4200, 5), "damaged", 999_999)
    assert decision.allowed is True
    assert decision.amount_cents == 4200


def test_changed_mind_window_is_shorter() -> None:
    allowed = decide(OrderView(2700, 10), "changed_mind", 2700)
    late = decide(OrderView(2700, 20), "changed_mind", 2700)
    assert allowed.allowed is True
    assert late.code == "outside_window"


def test_zero_unknown_and_empty_balance() -> None:
    order = OrderView(4200, 5)
    assert decide(order, "damaged", 0).code == "zero_amount"
    assert decide(order, "vip_override", 100).code == "unknown_reason"
    assert decide(OrderView(0, 4), "damaged", 100).code == "already_refunded"
    assert decide(None, "damaged", 100).code == "not_found"
