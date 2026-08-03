"""Order domain: `orders` and `order_items` (Phase 2 §3.8-3.9).

`orders.promotion_id` was added in Batch 2 as a plain nullable column with
no foreign key, because `promotions` didn't exist in metadata yet at that
point in the build-out. Now that `Promotion` exists (Batch 3), the FK
constraint is added here — Alembic will emit this as a follow-up
`ALTER TABLE ... ADD CONSTRAINT` on top of the Batch 2 migration, not a
schema redesign. The end state matches the approved Phase 2 design exactly.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
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
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from querymind.models.customer import Customer
    from querymind.models.payment import Payment
    from querymind.models.product import Product
    from querymind.models.promotion import Promotion
    from querymind.models.returns import Return
    from querymind.models.review import ProductReview
    from querymind.models.shipment import Shipment


class OrderStatus(str, Enum):
    """Phase 2 §3.8, CHECK IN (...)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class SalesChannel(str, Enum):
    """Phase 2 §3.8, CHECK IN (...)."""

    WEB = "web"
    MOBILE_APP = "mobile_app"
    MARKETPLACE = "marketplace"
    PHONE = "phone"


class Order(TimestampMixin, Base):
    """One row per customer order — the central fact table (Phase 2 §3.8)."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_order_date", "order_date"),
        Index("ix_orders_order_status", "order_status"),
        Index("ix_orders_sales_channel", "sales_channel"),
        Index("ix_orders_customer_id_order_date", "customer_id", "order_date"),
        Index("ix_orders_promotion_id", "promotion_id"),
        CheckConstraint("subtotal_amount >= 0", name="subtotal_amount_non_negative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_non_negative"),
        CheckConstraint("tax_amount >= 0", name="tax_amount_non_negative"),
        CheckConstraint("shipping_amount >= 0", name="shipping_amount_non_negative"),
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
    )

    order_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False
    )
    promotion_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("promotions.promotion_id", ondelete="RESTRICT")
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    order_status: Mapped[OrderStatus] = mapped_column(
        SAEnum(
            OrderStatus,
            name="order_status_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=OrderStatus.PENDING.value,
    )
    sales_channel: Mapped[SalesChannel] = mapped_column(
        SAEnum(
            SalesChannel,
            name="sales_channel_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=SalesChannel.WEB.value,
    )
    shipping_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state_province: Mapped[str | None] = mapped_column(String(100))
    shipping_postal_code: Mapped[str | None] = mapped_column(String(20))
    shipping_country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    subtotal_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    shipping_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")

    customer: Mapped[Customer] = relationship(back_populates="orders")
    promotion: Mapped[Promotion | None] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order")
    payments: Mapped[list[Payment]] = relationship(back_populates="order")
    shipments: Mapped[list[Shipment]] = relationship(back_populates="order")


class OrderItem(CreatedAtMixin, Base):
    """One product line within an order (Phase 2 §3.9).

    `unit_price` is a historical snapshot of the price actually charged —
    see the module-level design note in Phase 2 §3.9/Appendix: it is
    deliberately decoupled from `products.unit_price` (today's catalog
    price).
    """

    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_id_product_id"),
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
        Index("ix_order_items_product_id_order_id", "product_id", "order_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_non_negative"),
        CheckConstraint("line_total >= 0", name="line_total_non_negative"),
    )

    order_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="order_items")
    review: Mapped[ProductReview | None] = relationship(back_populates="order_item", uselist=False)
    returns: Mapped[list[Return]] = relationship(back_populates="order_item")
