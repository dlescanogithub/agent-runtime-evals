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
