"""add api_keys table

Revision ID: 5e835fc4abe5
Revises: f76b40117bc0
Create Date: 2026-08-10 00:00:00.000000

Additive only: a new table, no change to any existing one. Targets `AuthBase.metadata` (the
same non-business registry `users`/`refresh_tokens` already live on -- see
`querymind.auth.models`'s own module docstring for why: an API key must stay just as invisible
to the NLU/schema-linking layer as a user's password hash already is), so `alembic/env.py`'s
`target_metadata = Base.metadata` (the business schema) never sees this table either.

Mirrors `refresh_tokens`' own shape closely (a `user_id` FK with `ondelete=CASCADE`, a unique
lookup column) plus the columns `querymind.auth.models.ApiKey` adds beyond that: `key_prefix`
(plaintext, display-only), `name`, `expires_at`, `last_used_at`, `revoked_at`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e835fc4abe5"
down_revision: str | None = "f76b40117bc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_keys_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
