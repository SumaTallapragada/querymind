"""Catalog domain: `product_categories` and `products` (Phase 2 §3.3, §3.5)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from querymind.models.inventory import Inventory
    from querymind.models.order import OrderItem
    from querymind.models.review import ProductReview
    from querymind.models.supplier import Supplier


class ProductCategory(CreatedAtMixin, SoftDeleteMixin, Base):
    """Self-referencing category taxonomy node (Phase 2 §3.3)."""

    __tablename__ = "product_categories"
    __table_args__ = (
        UniqueConstraint(
            "parent_category_id",
            "category_name",
            name="uq_product_categories_parent_category_id_category_name",
        ),
        Index("ix_product_categories_parent_category_id", "parent_category_id"),
        Index("ix_product_categories_category_name", "category_name"),
    )

    category_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    parent_category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("product_categories.category_id", ondelete="RESTRICT")
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_path: Mapped[str | None] = mapped_column(String(500))

    parent: Mapped[ProductCategory | None] = relationship(
        remote_side="ProductCategory.category_id", back_populates="children"
    )
    children: Mapped[list[ProductCategory]] = relationship(back_populates="parent")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(TimestampMixin, SoftDeleteMixin, Base):
    """The sellable catalog item (Phase 2 §3.5)."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_supplier_id", "supplier_id"),
        Index("ix_products_product_name", "product_name"),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_launch_date", "launch_date"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("cost_price >= 0", name="cost_price_non_negative"),
    )

    product_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.category_id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 3))
    launch_date: Mapped[date | None] = mapped_column(Date)

    category: Mapped[ProductCategory] = relationship(back_populates="products")
    supplier: Mapped[Supplier] = relationship(back_populates="products")
    inventory: Mapped[list[Inventory]] = relationship(back_populates="product")
    order_items: Mapped[list[OrderItem]] = relationship(back_populates="product")
    reviews: Mapped[list[ProductReview]] = relationship(back_populates="product")
