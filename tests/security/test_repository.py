"""Integration tests for `AuditRepository` against the real, already-running local Postgres
instance -- no mocks, no fakes, mirroring `tests/auth/test_repository.py`'s own "real
infrastructure" precedent. Every test runs against the real `audit_log` table (Alembic revision
`0846b7c2fbf3`); the module-local `_clean_tables` fixture below deletes `audit_log` and `users`
after every test, so this file's own tests never depend on execution order or leftover state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.auth.models import User
from querymind.auth.repository import AuthenticationRepository
from querymind.security.models import AuditLog
from querymind.security.repository import AuditRepository


@pytest.fixture(autouse=True)
async def _clean_tables(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[None]:
    yield
    async with session_factory() as session:
        await session.execute(delete(AuditLog))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
def repository(session_factory: async_sessionmaker[AsyncSession]) -> AuditRepository:
    return AuditRepository(session_factory)


@pytest.fixture
def auth_repository(session_factory: async_sessionmaker[AsyncSession]) -> AuthenticationRepository:
    return AuthenticationRepository(session_factory)


class TestCreate:
    async def test_persists_and_returns_every_field(self, repository: AuditRepository) -> None:
        record = await repository.create(
            event_type="login_success",
            success=True,
            actor_user_id=None,
            actor_username="alice",
            ip_address="127.0.0.1",
            user_agent="curl/8.0",
            request_id="req-1",
            correlation_id="corr-1",
            resource="/api/v1/auth/login",
            event_metadata={"note": "ok"},
        )

        assert record.id is not None
        assert record.event_type == "login_success"
        assert record.success is True
        assert record.actor_username == "alice"
        assert record.ip_address == "127.0.0.1"
        assert record.user_agent == "curl/8.0"
        assert record.request_id == "req-1"
        assert record.correlation_id == "corr-1"
        assert record.resource == "/api/v1/auth/login"
        assert record.event_metadata == {"note": "ok"}
        assert record.created_at is not None

    async def test_defaults_every_optional_field_to_none(self, repository: AuditRepository) -> None:
        record = await repository.create(event_type="logout", success=True)

        assert record.actor_user_id is None
        assert record.actor_username is None
        assert record.ip_address is None
        assert record.user_agent is None
        assert record.request_id is None
        assert record.correlation_id is None
        assert record.resource is None
        assert record.event_metadata is None

    async def test_records_a_failure_event(self, repository: AuditRepository) -> None:
        record = await repository.create(
            event_type="login_failure", success=False, actor_username="unknown_user"
        )

        assert record.success is False
        assert record.event_type == "login_failure"


class TestActorForeignKey:
    async def test_links_to_a_real_user(
        self, repository: AuditRepository, auth_repository: AuthenticationRepository
    ) -> None:
        user = await auth_repository.create_user(
            username="audit_owner", email="audit_owner@example.com", password_hash="hash"
        )

        record = await repository.create(
            event_type="login_success",
            success=True,
            actor_user_id=user.id,
            actor_username="audit_owner",
        )

        assert record.actor_user_id == user.id

    async def test_on_delete_set_null_when_the_user_is_later_deleted(
        self,
        repository: AuditRepository,
        auth_repository: AuthenticationRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Deliberately different from `RefreshToken`/`ApiKey`'s own `ON DELETE CASCADE` --
        `AuditLog.actor_user_id`'s FK is `SET NULL`, so a user's audit history outlives their
        account instead of disappearing with it (see `AuditLog`'s own docstring).
        """
        user = await auth_repository.create_user(
            username="audit_deleted", email="audit_deleted@example.com", password_hash="hash"
        )
        record = await repository.create(
            event_type="login_success",
            success=True,
            actor_user_id=user.id,
            actor_username="audit_deleted",
        )

        async with session_factory() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            await session.delete(db_user)
            await session.commit()

        async with session_factory() as session:
            refreshed = await session.get(AuditLog, record.id)
            assert refreshed is not None
            assert refreshed.actor_user_id is None
            # `actor_username` was captured independently -- the record stays readable even
            # though the FK itself was nulled out by the user's deletion.
            assert refreshed.actor_username == "audit_deleted"

    async def test_a_null_actor_user_id_is_allowed(self, repository: AuditRepository) -> None:
        """Every failed-login-for-an-unknown-username event has no real user to link to at
        all -- must not raise a not-null/FK violation.
        """
        record = await repository.create(
            event_type="login_failure", success=False, actor_username="never_registered"
        )

        assert record.actor_user_id is None
