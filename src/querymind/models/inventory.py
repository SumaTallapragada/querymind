"""Fulfillment domain: `warehouses` and `inventory` (Phase 2 §3.6-3.7)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from querymind.models.product import Product
    from querymind.models.shipment import Shipment


class Warehouse(CreatedAtMixin, SoftDeleteMixin, Base):
    """A physical fulfillment center (Phase 2 §3.6)."""

    __tablename__ = "warehouses"
    __table_args__ = (Index("ix_warehouses_country_code", "country_code"),)

    warehouse_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    warehouse_name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)

    inventory: Mapped[list[Inventory]] = relationship(back_populates="warehouse")
    shipments: Mapped[list[Shipment]] = relationship(back_populates="warehouse")


class Inventory(Base):
    """Stock level of one product at one warehouse (Phase 2 §3.7).

    Only carries `updated_at` (no `created_at`) per the approved design, so it
    does not use `CreatedAtMixin`/`TimestampMixin` — a mutable stock snapshot
    has no meaningful "row created" moment worth tracking separately.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_inventory_product_id_warehouse_id"),
        Index("ix_inventory_product_id", "product_id"),
        Index("ix_inventory_warehouse_id", "warehouse_id"),
        Index("ix_inventory_quantity_on_hand", "quantity_on_hand"),
        CheckConstraint("quantity_on_hand >= 0", name="quantity_on_hand_non_negative"),
        CheckConstraint("reorder_level >= 0", name="reorder_level_non_negative"),
    )

    inventory_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.warehouse_id", ondelete="RESTRICT"), nullable=False
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reorder_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship(back_populates="inventory")
    warehouse: Mapped[Warehouse] = relationship(back_populates="inventory")
