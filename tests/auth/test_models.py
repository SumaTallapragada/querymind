"""Unit tests for the `User`/`RefreshToken` ORM model *definitions* -- table, column, and
constraint metadata only, via SQLAlchemy introspection, no database connection at all. Real
persistence behavior (uniqueness enforcement, cascade delete) is `test_repository.py`'s job,
against the real database.
"""

from __future__ import annotations

from typing import cast

import sqlalchemy as sa

from querymind.auth.models import AuthBase, RefreshToken, User, UserRole
from querymind.models.base import Base


def _primary_key_constraint(table: sa.FromClause) -> sa.PrimaryKeyConstraint:
    # `__table__`'s stub type (`FromClause`) is broader than its actual runtime type (`Table`,
    # which alone has `.constraints`) -- a known SQLAlchemy stub imprecision for the declarative
    # `__table__` class attribute, not a real ambiguity here.
    real_table = cast(sa.Table, table)
    return next(c for c in real_table.constraints if isinstance(c, sa.PrimaryKeyConstraint))


class TestAuthBaseIsolation:
    """The one property this phase's whole design hinges on -- see `models.py`'s own docstring:
    the auth schema must never be visible to `MetadataExtractor(Base.registry)`, which is what
    the NLU/schema-linking layer treats as "every table a question may be answered against."
    """

    def test_auth_tables_are_not_registered_on_the_business_schema_base(self) -> None:
        assert "users" not in Base.metadata.tables
        assert "refresh_tokens" not in Base.metadata.tables

    def test_auth_tables_are_registered_on_their_own_base(self) -> None:
        assert "users" in AuthBase.metadata.tables
        assert "refresh_tokens" in AuthBase.metadata.tables

    def test_auth_base_and_business_base_use_different_metadata(self) -> None:
        assert AuthBase.metadata is not Base.metadata


class TestUserTable:
    def test_table_name(self) -> None:
        assert User.__tablename__ == "users"

    def test_expected_columns_exist(self) -> None:
        columns = set(User.__table__.columns.keys())
        expected = {
            "id",
            "username",
            "email",
            "password_hash",
            "is_active",
            "is_superuser",
            "created_at",
            "updated_at",
        }
        assert expected <= columns

    def test_id_is_the_primary_key(self) -> None:
        assert User.__table__.columns["id"].primary_key is True

    def test_username_is_unique_and_not_nullable(self) -> None:
        column = User.__table__.columns["username"]
        assert column.unique is True
        assert column.nullable is False

    def test_email_is_unique_and_not_nullable(self) -> None:
        column = User.__table__.columns["email"]
        assert column.unique is True
        assert column.nullable is False

    def test_password_hash_is_not_nullable(self) -> None:
        assert User.__table__.columns["password_hash"].nullable is False

    def test_is_active_defaults_true(self) -> None:
        column = User.__table__.columns["is_active"]
        assert column.nullable is False
        assert column.server_default is not None
        assert column.server_default.arg == "true"

    def test_is_superuser_defaults_false(self) -> None:
        column = User.__table__.columns["is_superuser"]
        assert column.nullable is False
        assert column.server_default is not None
        assert column.server_default.arg == "false"

    def test_created_at_and_updated_at_are_timezone_aware(self) -> None:
        created_at_type = User.__table__.columns["created_at"].type
        updated_at_type = User.__table__.columns["updated_at"].type
        assert isinstance(created_at_type, sa.DateTime)
        assert isinstance(updated_at_type, sa.DateTime)
        assert created_at_type.timezone is True
        assert updated_at_type.timezone is True

    def test_has_a_refresh_tokens_relationship(self) -> None:
        assert hasattr(User, "refresh_tokens")


class TestUserRole:
    """`UserRole` (Phase 22B) -- exactly three roles, ranked `ADMIN` > `ANALYST` > `VIEWER`
    (the ranking itself lives on `AuthenticationService._ROLE_RANK`, not here; this only
    checks the enum's own shape).
    """

    def test_has_exactly_three_members(self) -> None:
        assert {member.value for member in UserRole} == {"admin", "analyst", "viewer"}

    def test_is_a_str_enum(self) -> None:
        assert UserRole.ADMIN == "admin"
        assert isinstance(UserRole.ADMIN, str)


class TestUserRoleColumn:
    """`role` (Phase 22B) -- additive: a `NOT NULL` column with a database-level default, so
    `alembic/versions/f76b40117bc0_add_role_column_to_users.py` never breaks an existing row.
    `test_repository.py::TestCreateUser::test_defaults_role_to_analyst` proves the default is
    actually applied by the real database, not just declared here.
    """

    def test_role_column_exists_and_is_not_nullable(self) -> None:
        column = User.__table__.columns["role"]
        assert column.nullable is False

    def test_role_defaults_to_analyst(self) -> None:
        column = User.__table__.columns["role"]
        assert column.server_default is not None
        assert column.server_default.arg == UserRole.ANALYST.value

    def test_role_is_backed_by_a_check_constraint_not_a_native_enum_type(self) -> None:
        """`native_enum=False` (see `models.py`'s own docstring for why): a `VARCHAR` column
        plus a `CHECK` constraint, not a Postgres `CREATE TYPE ... AS ENUM`, so a future fourth
        role never needs an `ALTER TYPE` migration.
        """
        column = User.__table__.columns["role"]
        assert isinstance(column.type, sa.Enum)
        assert column.type.native_enum is False


class TestRefreshTokenTable:
    def test_table_name(self) -> None:
        assert RefreshToken.__tablename__ == "refresh_tokens"

    def test_expected_columns_exist(self) -> None:
        columns = set(RefreshToken.__table__.columns.keys())
        expected = {"id", "user_id", "jti", "expires_at", "revoked", "created_at"}
        assert expected <= columns

    def test_id_is_the_primary_key(self) -> None:
        assert RefreshToken.__table__.columns["id"].primary_key is True

    def test_jti_is_unique_and_not_nullable(self) -> None:
        column = RefreshToken.__table__.columns["jti"]
        assert column.unique is True
        assert column.nullable is False

    def test_expires_at_is_not_nullable_and_timezone_aware(self) -> None:
        column = RefreshToken.__table__.columns["expires_at"]
        assert column.nullable is False
        assert isinstance(column.type, sa.DateTime)
        assert column.type.timezone is True

    def test_revoked_defaults_false(self) -> None:
        column = RefreshToken.__table__.columns["revoked"]
        assert column.nullable is False
        assert column.server_default is not None
        assert column.server_default.arg == "false"

    def test_user_id_foreign_key_targets_users_id(self) -> None:
        column = RefreshToken.__table__.columns["user_id"]
        assert column.nullable is False
        foreign_keys = list(column.foreign_keys)
        assert len(foreign_keys) == 1
        assert foreign_keys[0].target_fullname == "users.id"

    def test_foreign_key_cascades_on_delete(self) -> None:
        column = RefreshToken.__table__.columns["user_id"]
        foreign_key = next(iter(column.foreign_keys))
        assert foreign_key.ondelete == "CASCADE"

    def test_has_a_user_relationship(self) -> None:
        assert hasattr(RefreshToken, "user")


class TestConstraintNaming:
    """Both tables use the same `NAMING_CONVENTION` as the business schema (`db/base.py`) --
    checked here since a hand-written Alembic migration (see `alembic/versions/`) depends on
    these exact names matching what the ORM models themselves would generate.
    """

    def test_user_primary_key_name(self) -> None:
        assert _primary_key_constraint(User.__table__).name == "pk_users"

    def test_refresh_token_primary_key_name(self) -> None:
        assert _primary_key_constraint(RefreshToken.__table__).name == "pk_refresh_tokens"

    def test_foreign_key_constraint_name(self) -> None:
        column = RefreshToken.__table__.columns["user_id"]
        foreign_key = next(iter(column.foreign_keys))
        assert foreign_key.constraint is not None
        assert foreign_key.constraint.name == "fk_refresh_tokens_user_id_users"
