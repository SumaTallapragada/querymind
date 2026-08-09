"""SQLAlchemy ORM models for authentication: `User`, `RefreshToken`.

Deliberately declared on their own `AuthBase` (this module's own `DeclarativeBase` subclass),
**not** `querymind.models.base.Base` -- the one the whole Phase 2 business schema
(`customers`, `orders`, ...) shares. `querymind.api.container.ApplicationContainer.build`
constructs `MetadataRegistry` from `MetadataExtractor(Base.registry)`, which is what the NLU/
schema-linking layer treats as "every table a natural-language question may be answered
against." Registering `users`/`refresh_tokens` on that same `Base` would silently make them
visible to SQL generation -- letting a generated query touch `password_hash` -- which is both a
real security defect and a violation of this phase's "do not modify QueryMind pipeline logic"
constraint (the pipeline's visible schema must stay exactly what it already was). A second,
independent `DeclarativeBase` makes that impossible by construction, not by convention.

Alembic migrations for these two tables are still hand-authored against this same metadata
(see `alembic/versions/`) -- `alembic/env.py` is intentionally left untouched this phase (its
`target_metadata` stays `Base.metadata` only), so autogenerate never sees `AuthBase.metadata`;
a hand-written migration is what keeps that true while still shipping the tables.

Reuses `querymind.models.mixins`' `TimestampMixin`/`CreatedAtMixin`/`SoftDeleteMixin` -- safe to
do without pulling in `Base` itself, since those mixins are plain column-contributing classes
with no metadata/registry of their own (verified: `querymind/models/mixins.py` has no import of
`querymind.models.base`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from querymind.db.base import NAMING_CONVENTION
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin, TimestampMixin


class AuthBase(DeclarativeBase):
    """Declarative base for the authentication schema only -- see module docstring for why this
    is not `querymind.models.base.Base`. Reuses the same naming convention for consistency
    (stable, reproducible constraint/index names), not the same metadata/registry.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(TimestampMixin, SoftDeleteMixin, AuthBase):
    """One row per registered account. `SoftDeleteMixin` supplies `is_active` -- the same
    "account enabled" meaning it has everywhere else in this codebase, reused rather than
    redeclared.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(CreatedAtMixin, AuthBase):
    """One row per issued refresh token -- the persistence side of `querymind.auth.jwt`'s
    stateless refresh tokens: a refresh JWT's signature alone proves it was issued by this
    server, but only this table can say whether it has since been revoked (`logout`) or
    rotated away (`refresh_tokens`), which a JWT's own contents can never express.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
