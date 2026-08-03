"""Reusable business rule classes for the simulation engine.

Each module defines one domain's rule class (e.g. `CustomerRules`,
`OrderRules`), built from a `SeedConfig` and an optional calendar/rng —
see `BaseRules` for the shared construction contract and what these
classes are (and deliberately are not): no Faker calls, no ORM inserts,
no database sessions, no commits.
"""

from querymind.seeds.rules.base import BaseRules
from querymind.seeds.rules.customer import CustomerRules
from querymind.seeds.rules.inventory import InventoryRules
from querymind.seeds.rules.order import OrderRules
from querymind.seeds.rules.payment import PaymentRules
from querymind.seeds.rules.promotion import PromotionRules
from querymind.seeds.rules.returns import ReturnRules
from querymind.seeds.rules.review import ReviewRules
from querymind.seeds.rules.shipment import ShipmentRules

__all__ = [
    "BaseRules",
    "CustomerRules",
    "InventoryRules",
    "OrderRules",
    "PaymentRules",
    "PromotionRules",
    "ReturnRules",
    "ReviewRules",
    "ShipmentRules",
]
