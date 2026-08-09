"""add role column to users

Revision ID: f76b40117bc0
Revises: 3daffa332d31
Create Date: 2026-08-09 08:22:03.664575

Additive only: one nullable=False column with a server_default, so every existing row is
backfilled to 'analyst' by Postgres itself as part of the same DDL statement -- there is no
separate UPDATE step, and no existing row is ever left without a role. Matches
querymind.auth.models.User.role exactly (same enum values, same non-native CHECK-constraint
encoding queymind.models.customer.CustomerSegment already established -- see that model's own
precedent, mirrored here rather than a native Postgres ENUM type).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f76b40117bc0"
down_revision: str | None = "3daffa332d31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "analyst",
                "viewer",
                name="user_role_valid_values",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="analyst",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
