"""End-to-end tests against the real, fully wired authentication stack.

Wires the real `AuthenticationService` on top of the real `AuthenticationRepository` (the same
`Settings`/`create_engine` the application itself uses) -- no mocks, no fakes -- run against the
real, already-running local Postgres instance and its real `users`/`refresh_tokens` tables
(Alembic revision `3daffa332d31`). Mirrors `tests/sql_execution/test_integration.py`'s "real
components, real data" precedent. `test_service.py` already covers every business-rule branch
against a fake repository with no I/O; this file exists to prove the same rules still hold with
the real database underneath -- lookups, unique constraints, and cascade delete included.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.auth.exceptions import (
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
)
from querymind.auth.jwt import decode_token
from querymind.auth.models import RefreshToken, User
from querymind.auth.repository import AuthenticationRepository
from querymind.auth.service import AuthenticationService
from tests.auth.conftest import TEST_JWT_SECRET_KEY


@pytest.fixture(autouse=True)
async def _clean_auth_tables(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """See `test_repository.py`'s identical fixture -- module-local so no other test file in
    this package is affected.
    """
    yield
    async with session_factory() as session:
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
def service(session_factory: async_sessionmaker[AsyncSession]) -> AuthenticationService:
    repository = AuthenticationRepository(session_factory)
    return AuthenticationService(repository, jwt_secret_key=TEST_JWT_SECRET_KEY)


class TestRegistrationAndLogin:
    async def test_a_registered_user_can_log_in_with_the_right_password(
        self, service: AuthenticationService
    ) -> None:
        await service.register_user(
            username="alice", email="alice@example.com", password="correct-password"
        )

        user = await service.authenticate("alice", "correct-password")

        assert user.username == "alice"
        assert user.email == "alice@example.com"

    async def test_the_password_is_never_stored_in_plaintext(
        self, service: AuthenticationService, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await service.register_user(
            username="bob", email="bob@example.com", password="a-real-password"
        )

        async with session_factory() as session:
            result = await session.execute(select(User).where(User.username == "bob"))
            stored = result.scalar_one()

        assert stored.password_hash != "a-real-password"
        assert stored.password_hash.startswith("$argon2")

    async def test_login_fails_with_the_wrong_password(
        self, service: AuthenticationService
    ) -> None:
        await service.register_user(
            username="carol", email="carol@example.com", password="correct-password"
        )

        with pytest.raises(InvalidCredentialsError):
            await service.authenticate("carol", "wrong-password")

    async def test_registering_the_same_username_twice_fails(
        self, service: AuthenticationService
    ) -> None:
        await service.register_user(
            username="dave", email="dave1@example.com", password="password123"
        )

        with pytest.raises(DuplicateUserError):
            await service.register_user(
                username="dave", email="dave2@example.com", password="password123"
            )


class TestFullTokenLifecycle:
    """register -> login -> issue tokens -> refresh (rotate) -> logout, against real Postgres."""

    async def test_the_complete_lifecycle(self, service: AuthenticationService) -> None:
        await service.register_user(
            username="erin", email="erin@example.com", password="password123"
        )
        user = await service.authenticate("erin", "password123")

        tokens = await service.create_token_pair(user.id)
        assert tokens.access_token
        assert tokens.refresh_token

        rotated = await service.refresh_tokens(tokens.refresh_token)
        assert rotated.refresh_token != tokens.refresh_token

        with pytest.raises(RefreshTokenRevokedError):
            await service.validate_refresh_token(tokens.refresh_token)

        await service.logout(rotated.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.validate_refresh_token(rotated.refresh_token)

    async def test_refresh_tokens_are_persisted_and_independently_queryable(
        self, service: AuthenticationService, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await service.register_user(
            username="frank", email="frank@example.com", password="password123"
        )
        user = await service.authenticate("frank", "password123")
        tokens = await service.create_token_pair(user.id)
        claims = decode_token(tokens.refresh_token, secret_key=TEST_JWT_SECRET_KEY)

        async with session_factory() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.jti == claims.jti)
            )
            row = result.scalar_one()

        assert row.user_id == user.id
        assert row.revoked is False

    async def test_deleting_the_user_cascades_to_their_refresh_tokens(
        self, service: AuthenticationService, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await service.register_user(
            username="gina", email="gina@example.com", password="password123"
        )
        user = await service.authenticate("gina", "password123")
        tokens = await service.create_token_pair(user.id)

        async with session_factory() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            await session.delete(db_user)
            await session.commit()

        # The refresh token row is gone too (ON DELETE CASCADE) -- validate_refresh_token now
        # reports it as never issued, not merely "user not found."
        with pytest.raises(InvalidTokenError):
            await service.validate_refresh_token(tokens.refresh_token)
