from agent_runtime.catalog import OrderCatalog
from agent_runtime.store import SQLiteStore
from agent_runtime.tools import ToolService


def test_invalid_email_never_asks_for_review(config) -> None:
    service = ToolService(OrderCatalog(), SQLiteStore(config.database_path))
    error = service.validate(
        "send_email",
        {
            "body": "hello",
            "order_id": "LG-1001",
            "subject": "hi",
            "to": "attacker@evil.test",
        },
    )
    assert error is not None
    assert error["ok"] is False


def test_zero_and_negative_refunds_are_refused(config) -> None:
    store = SQLiteStore(config.database_path)
    service = ToolService(OrderCatalog(), store)
    for amount in (0, -5):
        arguments = {"amount_cents": amount, "order_id": "LG-1001", "reason": "damaged"}
        proposed = service.validate("send_refund", arguments)
        assert proposed is not None
        assert proposed["ok"] is False
        executed = service.execute("send_refund", arguments)
        assert executed["ok"] is False
    assert store.count_effects("send_refund") == 0


def test_a_refund_above_the_request_is_rejected(config) -> None:
    store = SQLiteStore(config.database_path)
    run = store.create_run(
        '{"customer_message":"Please refund 1000 cents.","intent":"refund",'
        '"order_id":"LG-1001","reason":"damaged","requested_amount_cents":1000}',
        config.run_budget_micro_usd,
    )
    service = ToolService(OrderCatalog(), store)
    arguments = {"amount_cents": 4200, "order_id": "LG-1001", "reason": "damaged"}
    proposed = service.validate("send_refund", arguments, run.id)
    assert proposed is not None
    assert proposed["ok"] is False
    error = proposed["error"]
    assert isinstance(error, dict)
    assert error["code"] == "above_requested"
    executed = service.execute("send_refund", arguments, run.id)
    assert executed["ok"] is False
    assert store.count_effects("send_refund") == 0
    within = service.validate(
        "send_refund",
        {"amount_cents": 1000, "order_id": "LG-1001", "reason": "damaged"},
        run.id,
    )
    assert within is not None
    within_error = within["error"]
    assert isinstance(within_error, dict)
    assert within_error["code"] == "lookup_required"


def test_over_cap_amount_is_rejected_before_any_effect(config) -> None:
    store = SQLiteStore(config.database_path)
    service = ToolService(OrderCatalog(), store)
    error = service.validate(
        "send_refund",
        {"amount_cents": 100_001, "order_id": "LG-1001", "reason": "damaged"},
    )
    assert error is not None
    assert store.count_effects("send_refund") == 0


def test_duplicate_refund_does_not_pay_twice(config) -> None:
    store = SQLiteStore(config.database_path)
    service = ToolService(OrderCatalog(), store)
    args = {"amount_cents": 4200, "order_id": "LG-1001", "reason": "damaged"}
    first = service.execute("send_refund", args)
    second = service.execute("send_refund", args)
    assert first == second
    assert store.refunded_cents("LG-1001") == 4200
    assert store.count_effects("send_refund") == 1


def test_a_substituted_reason_never_reaches_the_gate(config) -> None:
    store = SQLiteStore(config.database_path)
    run = store.create_run(
        '{"customer_message":"vip","intent":"refund","order_id":"LG-1001",'
        '"reason":"vip_override","requested_amount_cents":4200}',
        config.run_budget_micro_usd,
    )
    service = ToolService(OrderCatalog(), store)
    arguments = {"amount_cents": 4200, "order_id": "LG-1001", "reason": "damaged"}
    proposed = service.validate("send_refund", arguments, run.id)
    assert proposed is not None
    assert proposed["ok"] is False
    error = proposed["error"]
    assert isinstance(error, dict)
    assert error["code"] == "reason_mismatch"
    executed = service.execute("send_refund", arguments, run.id)
    assert executed["ok"] is False
    assert store.count_effects("send_refund") == 0


def test_an_email_is_refused_when_the_reason_is_not_a_refund(config) -> None:
    store = SQLiteStore(config.database_path)
    run = store.create_run(
        '{"customer_message":"vip","intent":"refund","order_id":"LG-1001",'
        '"reason":"vip_override","requested_amount_cents":4200}',
        config.run_budget_micro_usd,
    )
    service = ToolService(OrderCatalog(), store)
    arguments = {
        "body": "We are writing about your order.",
        "order_id": "LG-1001",
        "subject": "Update",
        "to": "avery.chen@lumen-goods.example",
    }
    proposed = service.validate("send_email", arguments, run.id)
    assert proposed is not None
    error = proposed["error"]
    assert isinstance(error, dict)
    assert error["code"] == "email_not_warranted"
    executed = service.execute("send_email", arguments, run.id)
    assert executed["ok"] is False
    assert store.count_effects("send_email") == 0


def test_changed_mind_inside_the_window_may_email(config) -> None:
    store = SQLiteStore(config.database_path)
    run = store.create_run(
        '{"customer_message":"unused","intent":"refund","order_id":"LG-1008",'
        '"reason":"changed_mind","requested_amount_cents":2700}',
        config.run_budget_micro_usd,
    )
    service = ToolService(OrderCatalog(), store)
    proposed = service.validate(
        "send_email",
        {
            "body": "We received your request.",
            "order_id": "LG-1008",
            "subject": "Update",
            "to": "elena.costa@lumen-goods.example",
        },
        run.id,
    )
    assert proposed is None


def test_unknown_policy_tells_the_model_to_stop(config) -> None:
    service = ToolService(OrderCatalog(), SQLiteStore(config.database_path))
    result = service.execute("lookup_policy", {"reason": "vip_override"})
    assert result["ok"] is True
    data = result["data"]
    assert isinstance(data, dict)
    assert data["known"] is False
    next_step = data["next_step"]
    assert isinstance(next_step, str)
    assert "send_refund" in next_step
    assert "denied" in next_step


def test_email_body_cannot_mention_another_order(config) -> None:
    service = ToolService(OrderCatalog(), SQLiteStore(config.database_path))
    error = service.validate(
        "send_email",
        {
            "body": "Also see LG-1010.",
            "order_id": "LG-1001",
            "subject": "Refund",
            "to": "avery.chen@lumen-goods.example",
        },
    )
    assert error is not None
