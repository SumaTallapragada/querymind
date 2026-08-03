"""Reverse-logistics domain: `returns` (Phase 2 §3.14).

Named `returns.py`, not `return.py` as in the batch plan's example listing:
`return` is a reserved Python keyword, and `from querymind.models.return
import Return` is a syntax error. The table name (`returns`) and the model
class name (`Return`, capitalized — not a keyword) are unaffected.
"""

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
    Integer,
    Numeric,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base

if TYPE_CHECKING:
    from querymind.models.order import OrderItem


class ReturnReason(str, Enum):
    """Phase 2 §3.14, CHECK IN (...)."""

    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    NO_LONGER_NEEDED = "no_longer_needed"
    DAMAGED_IN_SHIPPING = "damaged_in_shipping"
    NOT_AS_DESCRIBED = "not_as_described"
    OTHER = "other"


class ReturnStatus(str, Enum):
    """Phase 2 §3.14, CHECK IN (...)."""

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    COMPLETED = "completed"


class Return(Base):
    """One return request against a purchased line item (Phase 2 §3.14).

    Carries `requested_at`/`resolved_at` (not `created_at`/`updated_at`) per
    the approved design, so it uses neither timestamp mixin.
    """

    __tablename__ = "returns"
    __table_args__ = (
        Index("ix_returns_order_item_id", "order_item_id"),
        Index("ix_returns_return_status", "return_status"),
        Index("ix_returns_requested_at", "requested_at"),
        CheckConstraint("quantity_returned > 0", name="quantity_returned_positive"),
        CheckConstraint("refund_amount >= 0", name="refund_amount_non_negative"),
    )

    return_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order_items.order_item_id", ondelete="RESTRICT"), nullable=False
    )
    return_reason: Mapped[ReturnReason] = mapped_column(
        SAEnum(
            ReturnReason,
            name="return_reason_valid_values",
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    return_status: Mapped[ReturnStatus] = mapped_column(
        SAEnum(
            ReturnStatus,
            name="return_status_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ReturnStatus.REQUESTED.value,
    )
    quantity_returned: Mapped[int] = mapped_column(Integer, nullable=False)
    refund_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order_item: Mapped[OrderItem] = relationship(back_populates="returns")
