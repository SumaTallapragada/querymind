"""Payment domain: `payments` (Phase 2 §3.10)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from querymind.models.order import Order


class PaymentMethod(str, Enum):
    """Phase 2 §3.10, CHECK IN (...)."""

    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    GIFT_CARD = "gift_card"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, Enum):
    """Phase 2 §3.10, CHECK IN (...)."""

    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Payment(CreatedAtMixin, Base):
    """One payment transaction attempt against an order (Phase 2 §3.10).

    An order may have more than one row here — a failed attempt followed by
    a successful capture, or a partial refund.
    """

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_order_id", "order_id"),
        Index("ix_payments_payment_status", "payment_status"),
        Index("ix_payments_paid_at", "paid_at"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    payment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(
            PaymentMethod,
            name="payment_method_valid_values",
            native_enum=False,
            create_constraint=True,
            length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            name="payment_status_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=PaymentStatus.PENDING.value,
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_reference: Mapped[str | None] = mapped_column(String(100), unique=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payments")
