"""Customer feedback domain: `product_reviews` (Phase 2 §3.12)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base

if TYPE_CHECKING:
    from querymind.models.customer import Customer
    from querymind.models.order import OrderItem
    from querymind.models.product import Product


class ProductReview(Base):
    """Customer-authored product feedback (Phase 2 §3.12).

    Carries only `review_date` (no `created_at`/`updated_at`) per the
    approved design, so it uses neither timestamp mixin.
    """

    __tablename__ = "product_reviews"
    __table_args__ = (
        Index("ix_product_reviews_product_id", "product_id"),
        Index("ix_product_reviews_customer_id", "customer_id"),
        Index("ix_product_reviews_rating", "rating"),
        Index("ix_product_reviews_review_date", "review_date"),
        Index("ix_product_reviews_product_id_rating", "product_id", "rating"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_in_range"),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False
    )
    order_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("order_items.order_item_id", ondelete="SET NULL"),
        unique=True,
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    review_title: Mapped[str | None] = mapped_column(String(200))
    review_text: Mapped[str | None] = mapped_column(Text)
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    review_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="reviews")
    customer: Mapped[Customer] = relationship(back_populates="reviews")
    order_item: Mapped[OrderItem | None] = relationship(back_populates="review")
