"""Supplier domain: `suppliers` (Phase 2 §3.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from querymind.models.product import Product


class Supplier(CreatedAtMixin, SoftDeleteMixin, Base):
    """External vendor QueryMind sources products from (Phase 2 §3.4)."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_suppliers_supplier_name", "supplier_name"),
        Index("ix_suppliers_country_code", "country_code"),
        Index("ix_suppliers_is_active", "is_active"),
        CheckConstraint("lead_time_days >= 0", name="lead_time_days_non_negative"),
        CheckConstraint("rating BETWEEN 0 AND 5", name="rating_in_range"),
    )

    supplier_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    supplier_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))

    products: Mapped[list[Product]] = relationship(back_populates="supplier")
