"""`AuditLog` -- the durable, queryable half of Phase 22D's audit trail (the other half is a
structured `structlog` line; see `querymind.security.audit.AuditLogger`'s own docstring for why
both).

Targets `AuthBase.metadata` (`querymind.auth.models`), the same non-business declarative base
`users`/`refresh_tokens`/`api_keys` already share -- deliberately, not a third registry: an
audit record can carry a username, IP address, or user-agent, which must stay exactly as
invisible to the NLU/schema-linking layer as a password hash already is (see `AuthBase`'s own
module docstring for why that isolation exists at all). Owned by `querymind.security`, not
`querymind.auth`, because an audit trail is this package's concern, not an identity concern --
only the shared metadata registry is reused, nothing else.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from querymind.auth.models import AuthBase


class AuditLog(AuthBase):
    """One security-relevant event -- insert-only, never updated or deleted by application code
    (see `AuditRepository`'s own docstring). `actor_user_id` is nullable and `ON DELETE SET
    NULL` (not `CASCADE`): a user's audit history must outlive their account, unlike a
    `RefreshToken`/`ApiKey`, which is meaningless once its owner is gone. `actor_username` is
    captured independently so a record stays readable even when `actor_user_id` is `NULL` (e.g.
    a login failure for a username that was never valid, or a user later deleted).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: Small, structured, pre-sanitized extras only -- never a password, JWT, refresh token, raw
    #: API key, or `Authorization` header value. Every call site builds this dict from already-
    #: safe primitives (see `AuditLogger.record`'s own docstring); there is no code path here
    #: that could serialize a secret because none is ever passed in.
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
