"""Integration tests for `AuthenticationRepository` against the real, already-running local
Postgres instance -- no mocks, no fakes, mirroring `tests/sql_execution/test_integration.py`'s
"real infrastructure" precedent. Every test in this module runs against the real `users`/
`refresh_tokens` tables (Alembic revision `3daffa332d31`); the module-local `_clean_auth_tables`
fixture below deletes both after every test, so this file's own tests never depend on
execution order or leftover state from a previous run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.auth.models import ApiKey, RefreshToken, User, UserRole
from querymind.auth.repository import AuthenticationRepository


@pytest.fixture(autouse=True)
async def _clean_auth_tables(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Module-local (not in `tests/auth/conftest.py`) so only this file's tests -- and
    `test_integration.py`'s own identical fixture -- ever touch the database; every other test
    module in this package stays a pure unit test with no DB dependency at all.
    """
    yield
    async with session_factory() as session:
        await session.execute(delete(ApiKey))
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
def repository(session_factory: async_sessionmaker[AsyncSession]) -> AuthenticationRepository:
    return AuthenticationRepository(session_factory)


class TestCreateUser:
    async def test_creates_and_returns_a_persisted_user(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="alice", email="alice@example.com", password_hash="argon2-hash"
        )

        assert user.id is not None
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.password_hash == "argon2-hash"

    async def test_defaults_is_active_true_and_is_superuser_false(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="bob", email="bob@example.com", password_hash="hash"
        )

        assert user.is_active is True
        assert user.is_superuser is False

    async def test_honors_an_explicit_is_superuser(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="root", email="root@example.com", password_hash="hash", is_superuser=True
        )

        assert user.is_superuser is True

    async def test_sets_created_at_and_updated_at(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="carol", email="carol@example.com", password_hash="hash"
        )

        assert user.created_at is not None
        assert user.updated_at is not None

    async def test_defaults_role_to_analyst(self, repository: AuthenticationRepository) -> None:
        """Proves the real database applies `role`'s `server_default` -- `AuthenticationRepository.
        create_user` (deliberately, per Phase 22B's "no self-elevation" constraint) has no `role`
        parameter at all, so this is the only outcome a caller can ever get.
        """
        user = await repository.create_user(
            username="role_default", email="role_default@example.com", password_hash="hash"
        )

        assert user.role is UserRole.ANALYST

    async def test_duplicate_username_raises_integrity_error(
        self, repository: AuthenticationRepository
    ) -> None:
        await repository.create_user(
            username="dave", email="dave1@example.com", password_hash="hash"
        )

        with pytest.raises(IntegrityError):
            await repository.create_user(
                username="dave", email="dave2@example.com", password_hash="hash"
            )

    async def test_duplicate_email_raises_integrity_error(
        self, repository: AuthenticationRepository
    ) -> None:
        await repository.create_user(
            username="erin1", email="erin@example.com", password_hash="hash"
        )

        with pytest.raises(IntegrityError):
            await repository.create_user(
                username="erin2", email="erin@example.com", password_hash="hash"
            )


class TestRoleCheckConstraint:
    """Proves the real `CHECK` constraint (`ck_users_user_role_valid_values`, from
    `alembic/versions/f76b40117bc0_add_role_column_to_users.py`) itself rejects an invalid
    value -- via a raw `INSERT`, not `AuthenticationRepository`/the ORM, since SQLAlchemy's own
    `Enum` type would reject an invalid `UserRole` before a query is ever sent, which would
    prove Python-side validation works, not that the database's own constraint does.
    """

    async def test_rejects_a_role_value_outside_the_three_allowed_ones(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "INSERT INTO users (username, email, password_hash, role) "
                        "VALUES (:username, :email, :password_hash, :role)"
                    ),
                    {
                        "username": "role_constraint_test",
                        "email": "role_constraint_test@example.com",
                        "password_hash": "hash",
                        "role": "superadmin",
                    },
                )
            await session.rollback()


class TestGetByUsername:
    async def test_returns_the_matching_user(self, repository: AuthenticationRepository) -> None:
        created = await repository.create_user(
            username="frank", email="frank@example.com", password_hash="hash"
        )

        found = await repository.get_by_username("frank")

        assert found is not None
        assert found.id == created.id

    async def test_returns_none_when_not_found(self, repository: AuthenticationRepository) -> None:
        assert await repository.get_by_username("nobody-with-this-name") is None


class TestGetByEmail:
    async def test_returns_the_matching_user(self, repository: AuthenticationRepository) -> None:
        created = await repository.create_user(
            username="gina", email="gina@example.com", password_hash="hash"
        )

        found = await repository.get_by_email("gina@example.com")

        assert found is not None
        assert found.id == created.id

    async def test_returns_none_when_not_found(self, repository: AuthenticationRepository) -> None:
        assert await repository.get_by_email("nobody@example.com") is None


class TestGetById:
    async def test_returns_the_matching_user(self, repository: AuthenticationRepository) -> None:
        created = await repository.create_user(
            username="hank", email="hank@example.com", password_hash="hash"
        )

        found = await repository.get_by_id(created.id)

        assert found is not None
        assert found.username == "hank"

    async def test_returns_none_when_not_found(self, repository: AuthenticationRepository) -> None:
        assert await repository.get_by_id(999_999_999) is None


class TestRefreshTokenLifecycle:
    async def test_store_and_get_refresh_token_round_trips(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="ivy", email="ivy@example.com", password_hash="hash"
        )
        expires_at = datetime.now(UTC) + timedelta(days=14)

        stored = await repository.store_refresh_token(
            user_id=user.id, jti="jti-round-trip", expires_at=expires_at
        )
        assert stored.revoked is False

        fetched = await repository.get_refresh_token("jti-round-trip")
        assert fetched is not None
        assert fetched.user_id == user.id
        assert fetched.revoked is False

    async def test_get_refresh_token_returns_none_when_not_found(
        self, repository: AuthenticationRepository
    ) -> None:
        assert await repository.get_refresh_token("this-jti-was-never-issued") is None

    async def test_revoke_refresh_token_marks_it_revoked(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="jack", email="jack@example.com", password_hash="hash"
        )
        await repository.store_refresh_token(
            user_id=user.id, jti="jti-to-revoke", expires_at=datetime.now(UTC) + timedelta(days=1)
        )

        await repository.revoke_refresh_token("jti-to-revoke")

        fetched = await repository.get_refresh_token("jti-to-revoke")
        assert fetched is not None
        assert fetched.revoked is True

    async def test_revoke_refresh_token_is_a_no_op_for_an_unknown_jti(
        self, repository: AuthenticationRepository
    ) -> None:
        await repository.revoke_refresh_token("never-issued-jti")  # must not raise

    async def test_cascade_deletes_refresh_tokens_when_the_user_is_deleted(
        self,
        repository: AuthenticationRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await repository.create_user(
            username="kate", email="kate@example.com", password_hash="hash"
        )
        await repository.store_refresh_token(
            user_id=user.id, jti="jti-cascade", expires_at=datetime.now(UTC) + timedelta(days=1)
        )

        async with session_factory() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            await session.delete(db_user)
            await session.commit()

        assert await repository.get_refresh_token("jti-cascade") is None


class TestApiKeyLifecycle:
    async def test_create_and_get_by_hash_round_trips(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="liam", email="liam@example.com", password_hash="hash"
        )

        created = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_abcd1234",
            key_hash="a" * 64,
            name="CI pipeline",
            expires_at=None,
        )
        assert created.id is not None
        assert created.revoked_at is None
        assert created.last_used_at is None

        fetched = await repository.get_api_key_by_hash("a" * 64)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.user_id == user.id
        assert fetched.name == "CI pipeline"

    async def test_get_api_key_by_hash_returns_none_when_not_found(
        self, repository: AuthenticationRepository
    ) -> None:
        assert await repository.get_api_key_by_hash("never-issued-hash") is None

    async def test_get_api_key_by_id_returns_none_when_not_found(
        self, repository: AuthenticationRepository
    ) -> None:
        assert await repository.get_api_key_by_id(999_999_999) is None

    async def test_list_api_keys_for_user_orders_most_recent_first(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="mia", email="mia@example.com", password_hash="hash"
        )
        first = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_first111",
            key_hash="b" * 64,
            name="first",
            expires_at=None,
        )
        second = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_second22",
            key_hash="c" * 64,
            name="second",
            expires_at=None,
        )

        keys = await repository.list_api_keys_for_user(user.id)

        assert [key.id for key in keys] == [second.id, first.id]

    async def test_list_api_keys_never_returns_another_users_keys(
        self, repository: AuthenticationRepository
    ) -> None:
        owner = await repository.create_user(
            username="noah", email="noah@example.com", password_hash="hash"
        )
        other = await repository.create_user(
            username="olive", email="olive@example.com", password_hash="hash"
        )
        await repository.create_api_key(
            user_id=other.id,
            key_prefix="qm_other111",
            key_hash="d" * 64,
            name="not mine",
            expires_at=None,
        )

        assert await repository.list_api_keys_for_user(owner.id) == []

    async def test_revoke_api_key_sets_revoked_at(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="paul", email="paul@example.com", password_hash="hash"
        )
        created = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_revoke11",
            key_hash="e" * 64,
            name="to revoke",
            expires_at=None,
        )

        await repository.revoke_api_key(created.id)

        fetched = await repository.get_api_key_by_id(created.id)
        assert fetched is not None
        assert fetched.revoked_at is not None

    async def test_revoke_api_key_is_a_no_op_for_an_unknown_id(
        self, repository: AuthenticationRepository
    ) -> None:
        await repository.revoke_api_key(999_999_999)  # must not raise

    async def test_touch_api_key_last_used_sets_the_timestamp(
        self, repository: AuthenticationRepository
    ) -> None:
        user = await repository.create_user(
            username="quinn", email="quinn@example.com", password_hash="hash"
        )
        created = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_touch111",
            key_hash="f" * 64,
            name="touched",
            expires_at=None,
        )
        assert created.last_used_at is None

        await repository.touch_api_key_last_used(created.id)

        fetched = await repository.get_api_key_by_id(created.id)
        assert fetched is not None
        assert fetched.last_used_at is not None

    async def test_cascade_deletes_api_keys_when_the_user_is_deleted(
        self,
        repository: AuthenticationRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await repository.create_user(
            username="ruth", email="ruth@example.com", password_hash="hash"
        )
        created = await repository.create_api_key(
            user_id=user.id,
            key_prefix="qm_cascade1",
            key_hash="0" * 64,
            name="cascade",
            expires_at=None,
        )

        async with session_factory() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            await session.delete(db_user)
            await session.commit()

        assert await repository.get_api_key_by_id(created.id) is None
