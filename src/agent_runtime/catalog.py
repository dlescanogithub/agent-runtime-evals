"""Synthetic order book for Lumen Goods, a fictional home-goods retailer.

Nothing in this module is a real customer, order, or email. Addresses use the
reserved .example domain so they cannot be delivered.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.errors import TransientError


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_name: str
    email: str
    item: str
    total_cents: int
    refundable_cents: int
    days_since_delivery: int
    status: str


# refundable_cents is the original balance. Money already moved in this
# process is tracked in SQLite and subtracted at read time.
SYNTHETIC_ORDERS: dict[str, Order] = {
    "LG-1001": Order(
        "LG-1001",
        "Avery Chen",
        "avery.chen@lumen-goods.example",
        "Ceramic lamp",
        4200,
        4200,
        5,
        "delivered",
    ),
    "LG-1002": Order(
        "LG-1002",
        "Noor Rahman",
        "noor.rahman@lumen-goods.example",
        "Wool throw",
        3000,
        0,
        4,
        "refunded",
    ),
    "LG-1003": Order(
        "LG-1003",
        "Luis Ortega",
        "luis.ortega@lumen-goods.example",
        "Oak stool",
        8000,
        8000,
        45,
        "delivered",
    ),
    "LG-1005": Order(
        "LG-1005",
        "Mina Petrov",
        "mina.petrov@lumen-goods.example",
        "Tea set",
        900,
        900,
        2,
        "delivered",
    ),
    "LG-1006": Order(
        "LG-1006",
        "Jonah Blake",
        "jonah.blake@lumen-goods.example",
        "Desk lamp",
        6400,
        6400,
        3,
        "delivered",
    ),
    "LG-1007": Order(
        "LG-1007",
        "Priya Shah",
        "priya.shah@lumen-goods.example",
        "Linen sheets",
        5100,
        5100,
        6,
        "delivered",
    ),
    "LG-1008": Order(
        "LG-1008",
        "Elena Costa",
        "elena.costa@lumen-goods.example",
        "Wall clock",
        2700,
        2700,
        10,
        "delivered",
    ),
    "LG-1009": Order(
        "LG-1009",
        "Samir Haddad",
        "samir.haddad@lumen-goods.example",
        "Cutting board",
        2700,
        2700,
        20,
        "delivered",
    ),
    "LG-1010": Order(
        "LG-1010",
        "Ruth Keller",
        "ruth.keller@lumen-goods.example",
        "Bookshelf",
        15000,
        15000,
        12,
        "delivered",
    ),
}


class OrderCatalog:
    """Read-only view of the synthetic book. Writes go to the ledger, not here."""

    def get(self, order_id: str) -> Order | None:
        return SYNTHETIC_ORDERS.get(order_id)


class FlakyCatalog(OrderCatalog):
    """Test double. The first `failures` reads raise a retryable error."""

    def __init__(self, inner: OrderCatalog, failures: int) -> None:
        self._inner = inner
        self.failures_left = failures

    def get(self, order_id: str) -> Order | None:
        if self.failures_left > 0:
            self.failures_left -= 1
            raise TransientError("synthetic catalog timeout")
        return self._inner.get(order_id)
