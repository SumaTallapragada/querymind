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

`UserRole` (Phase 22B) is mapped the same way `querymind.models.customer.CustomerSegment` maps
its own enum -- `native_enum=False` (a `VARCHAR` + `CHECK` constraint, not a real Postgres
`ENUM` type, so adding a fourth role later is a plain, no-downtime column-constraint migration,
never an `ALTER TYPE`).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, MetaData, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from querymind.db.base import NAMING_CONVENTION
from querymind.models.mixins import CreatedAtMixin, SoftDeleteMixin, TimestampMixin


class UserRole(str, Enum):
    """The three roles this phase supports, ranked `ADMIN` > `ANALYST` > `VIEWER` -- see
    `AuthenticationService.require_role`'s own docstring for what "ranked" means for
    authorization (a higher role satisfies a lower requirement). Not a permissions/ABAC system:
    exactly these three values, checked by membership/rank, never stored anywhere but this one
    column (never in a JWT claim -- a role change takes effect on a caller's very next request,
    not only after their current tokens expire).
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


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
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role_valid_values",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=UserRole.ANALYST.value,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
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


class ApiKey(CreatedAtMixin, AuthBase):
    """One issued API key (Phase 22D) -- a second, machine-oriented credential resolving to the
    same `User` identity/role a JWT would, never a parallel permission system. Only `key_hash`
    (a SHA-256 digest, see `querymind.auth.api_keys`) is ever persisted; the raw key itself is
    never stored anywhere, matching `User.password_hash`'s own "never the secret itself" rule.

    `revoked_at` (nullable timestamp, not a bare `bool` the way `RefreshToken.revoked` is) records
    *when* a key was revoked, useful for audit review -- `RefreshToken` predates the audit-log
    table (Phase 22D) this could now be cross-referenced against, so this is a deliberately
    richer column than that earlier precedent, not an inconsistency with it.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")
