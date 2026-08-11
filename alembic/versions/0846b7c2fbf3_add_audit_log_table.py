"""add audit_log table

Revision ID: 0846b7c2fbf3
Revises: 5e835fc4abe5
Create Date: 2026-08-10 00:10:00.000000

Additive only: a new, insert-only table, no change to any existing one. Targets
`AuthBase.metadata` (see `querymind.security.models.AuditLog`'s own docstring for why: an audit
record can carry a username/IP/user-agent, which must stay as invisible to the NLU/schema-
linking layer as `users.password_hash` already is), so `alembic/env.py`'s
`target_metadata = Base.metadata` (the business schema) never sees this table either.

`actor_user_id`'s FK is `ON DELETE SET NULL`, not `CASCADE` -- deliberately different from every
other FK to `users.id` in this schema (`refresh_tokens.user_id`, `api_keys.user_id`, both
`CASCADE`): a user's audit history is meant to outlive their account, unlike a token or key,
which is meaningless once its owner is gone.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0846b7c2fbf3"
down_revision: str | None = "5e835fc4abe5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_username", sa.String(length=50), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("resource", sa.String(length=100), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_log_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"])
    op.create_index(op.f("ix_audit_log_event_type"), "audit_log", ["event_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_log_event_type"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_table("audit_log")
