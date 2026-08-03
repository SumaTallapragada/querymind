"""Reusable column mixins shared by ORM models.

Each mixin here exists because more than one Phase 2 table has the exact
same column, with the exact same type/nullability/default — not because
every table gets every mixin. Tables that only need one half of a pattern
(e.g. `inventory.updated_at` with no `created_at`) declare that column
directly on the model instead of forcing an ill-fitting mixin onto it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class CreatedAtMixin:
    """A single `created_at` audit column.

    Used by tables that record when a row was created but never mutate it
    afterward (e.g. `suppliers`, `warehouses`, `product_categories`,
    `customer_addresses`, `order_items`, `payments`, `shipments`,
    `promotions`).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TimestampMixin(CreatedAtMixin):
    """`created_at` plus `updated_at`.

    Used only by tables that are actually mutated after creation per the
    Phase 2 design: `customers`, `products`, `orders`.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """The `is_active` soft-delete flag.

    Used by every table the Phase 2 design marks as soft-deletable rather
    than physically deletable: `customers`, `product_categories`,
    `suppliers`, `products`, `warehouses`, `promotions`.
    """

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
