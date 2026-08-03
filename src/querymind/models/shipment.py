"""Fulfillment domain: `shipments` (Phase 2 §3.11)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from querymind.models.inventory import Warehouse
    from querymind.models.order import Order


class ShipmentStatus(str, Enum):
    """Phase 2 §3.11, CHECK IN (...)."""

    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETURNED_TO_SENDER = "returned_to_sender"


class Shipment(CreatedAtMixin, Base):
    """One physical shipment fulfilling all or part of an order (Phase 2 §3.11)."""

    __tablename__ = "shipments"
    __table_args__ = (
        Index("ix_shipments_order_id", "order_id"),
        Index("ix_shipments_warehouse_id", "warehouse_id"),
        Index("ix_shipments_shipment_status", "shipment_status"),
        Index("ix_shipments_shipped_at", "shipped_at"),
    )

    shipment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.warehouse_id", ondelete="RESTRICT"), nullable=False
    )
    carrier: Mapped[str | None] = mapped_column(String(50))
    tracking_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    shipment_status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(
            ShipmentStatus,
            name="shipment_status_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ShipmentStatus.PENDING.value,
    )
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="shipments")
    warehouse: Mapped[Warehouse] = relationship(back_populates="shipments")
