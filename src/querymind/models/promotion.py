"""Marketing domain: `promotions` (Phase 2 §3.13)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from querymind.models.order import Order


class DiscountType(str, Enum):
    """Phase 2 §3.13, CHECK IN (...)."""

    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class Promotion(CreatedAtMixin, SoftDeleteMixin, Base):
    """A discount code/campaign that can be applied to an order (Phase 2 §3.13)."""

    __tablename__ = "promotions"
    __table_args__ = (
        Index("ix_promotions_starts_at_ends_at", "starts_at", "ends_at"),
        Index("ix_promotions_is_active", "is_active"),
        CheckConstraint("discount_value >= 0", name="discount_value_non_negative"),
        CheckConstraint("ends_at > starts_at", name="ends_at_after_starts_at"),
    )

    promotion_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    promotion_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    promotion_name: Mapped[str] = mapped_column(String(150), nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(
            DiscountType,
            name="discount_type_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="promotion")
