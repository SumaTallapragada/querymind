"""Customer domain: `customers` and `customer_addresses` (Phase 2 §3.1-3.2)."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, BigInteger, Boolean, Date, ForeignKey, Identity, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from querymind.models.base import Base
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from querymind.models.order import Order
    from querymind.models.review import ProductReview


class CustomerSegment(str, Enum):
    """Marketing/pricing tier — Phase 2 §3.1, CHECK IN ('standard','vip','wholesale')."""

    STANDARD = "standard"
    VIP = "vip"
    WHOLESALE = "wholesale"


class AddressType(str, Enum):
    """Phase 2 §3.2, CHECK IN ('billing','shipping')."""

    BILLING = "billing"
    SHIPPING = "shipping"


class Customer(TimestampMixin, SoftDeleteMixin, Base):
    """One row per registered customer account (Phase 2 §3.1)."""

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_signup_date", "signup_date"),
        Index("ix_customers_customer_segment", "customer_segment"),
        Index("ix_customers_is_active", "is_active"),
    )

    customer_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    customer_segment: Mapped[CustomerSegment] = mapped_column(
        SAEnum(
            CustomerSegment,
            name="customer_segment_valid_values",
            native_enum=False,
            create_constraint=True,
            length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=CustomerSegment.STANDARD.value,
    )
    signup_date: Mapped[date] = mapped_column(Date, nullable=False)
    signup_channel: Mapped[str | None] = mapped_column(String(30))

    addresses: Mapped[list[CustomerAddress]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    orders: Mapped[list[Order]] = relationship(back_populates="customer")
    reviews: Mapped[list[ProductReview]] = relationship(back_populates="customer")


class CustomerAddress(CreatedAtMixin, Base):
    """A customer's saved address book entry (Phase 2 §3.2).

    Deliberately has no FK from `orders` — see Phase 2 §4/Appendix: order
    shipping addresses are a denormalized snapshot, not a live reference to
    this mutable table.
    """

    __tablename__ = "customer_addresses"
    __table_args__ = (
        Index("ix_customer_addresses_customer_id", "customer_id"),
        Index("ix_customer_addresses_country_code", "country_code"),
        Index(
            "ix_customer_addresses_one_default_per_type",
            "customer_id",
            "address_type",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

    address_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False
    )
    address_type: Mapped[AddressType] = mapped_column(
        SAEnum(
            AddressType,
            name="address_type_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="addresses")
