"""HTTP-level tests for Phase 22D's audit logging: the success half (`querymind.api.routers
.auth`, one line per route) and the failure half (`querymind.api.exception_handlers`, centralized
across every route). `AuditLoggerDep` is overridden with `FakeAuditLogger` throughout -- no real
database, mirroring `AuthenticationServiceDep`'s own `FakeAuthenticationService` pattern.

`tests/security/test_audit.py` covers `AuditLogger` itself (structlog + repository writes, the
best-effort swallow on a repository failure) in isolation; this file covers *which* event gets
recorded, with *what* fields, for each route -- the wiring, not the sink.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_audit_logger, get_authentication_service
from querymind.auth.exceptions import DuplicateUserError, InvalidCredentialsError, TokenExpiredError
from querymind.auth.models import UserRole
from querymind.security.audit import AuditEventType
from tests.api.conftest import (
    FakeAuditLogger,
    FakeAuthenticationService,
    make_api_key_created,
    make_token_pair,
    make_user_read,
)


def _install(app: FastAPI, fake: FakeAuthenticationService, audit: FakeAuditLogger) -> None:
    app.dependency_overrides[get_authentication_service] = lambda: fake
    # Covers the *success* half: every route's own `audit_logger: AuditLoggerDep` parameter
    # (querymind.api.routers.auth) resolves through FastAPI's DI, so this override reaches it.
    app.dependency_overrides[get_audit_logger] = lambda: audit
    # Covers the *failure* half: `querymind.api.exception_handlers` reads
    # `request.app.state.container.audit_logger` directly (mirroring how it already reads
    # `.container.logger` for `_log_and_respond`), never through `Depends()` -- `dependency_
    # overrides` above has no effect on it, so the (frozen, slotted) container itself needs
    # patching. `object.__setattr__` is the standard escape hatch for a frozen dataclass; this
    # is test-only and never runs in production code.
    object.__setattr__(app.state.container, "audit_logger", audit)


class TestRegistrationAudit:
    async def test_success_records_registration_with_the_new_user(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = make_user_read(id=5, username="alice")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "password123"},
        )

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.REGISTRATION
        assert record["success"] is True
        assert record["actor_user_id"] == 5
        assert record["actor_username"] == "alice"

    async def test_failure_records_registration_failure_with_the_attempted_username(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = DuplicateUserError("already taken")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.com", "password": "password123"},
        )

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.REGISTRATION_FAILURE
        assert record["success"] is False
        assert record["actor_username"] == "bob"

    async def test_the_password_never_appears_in_any_audit_record(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = make_user_read(username="carol")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/register",
            json={
                "username": "carol",
                "email": "carol@example.com",
                "password": "a-very-real-secret-password",
            },
        )

        assert "a-very-real-secret-password" not in str(audit.records)


class TestLoginAudit:
    async def test_success_records_login_success_with_the_authenticated_user(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = make_user_read(id=9, username="dave")
        fake.create_token_pair_result = make_token_pair()
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/login", json={"username": "dave", "password": "password123"}
        )

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.LOGIN_SUCCESS
        assert record["success"] is True
        assert record["actor_user_id"] == 9
        assert record["actor_username"] == "dave"

    async def test_failure_records_login_failure_with_the_attempted_username(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("bad credentials")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/login", json={"username": "erin", "password": "wrong-password"}
        )

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.LOGIN_FAILURE
        assert record["success"] is False
        assert record["actor_username"] == "erin"

    async def test_the_wrong_password_never_appears_in_any_audit_record(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("bad credentials")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/login",
            json={"username": "frank", "password": "a-guessed-secret-value"},
        )

        assert "a-guessed-secret-value" not in str(audit.records)


class TestRefreshAudit:
    async def test_success_records_refresh_success(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = make_token_pair()
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post("/api/v1/auth/refresh", json={"refresh_token": "some.refresh.token"})

        assert len(audit.records) == 1
        assert audit.records[0]["event_type"] is AuditEventType.REFRESH_SUCCESS
        assert audit.records[0]["success"] is True

    async def test_failure_records_refresh_failure(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = TokenExpiredError("expired")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post("/api/v1/auth/refresh", json={"refresh_token": "expired.token"})

        assert len(audit.records) == 1
        assert audit.records[0]["event_type"] is AuditEventType.REFRESH_FAILURE
        assert audit.records[0]["success"] is False

    async def test_the_refresh_token_never_appears_in_any_audit_record(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = TokenExpiredError("expired")
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "a-very-real-looking.jwt.token"}
        )

        assert "a-very-real-looking.jwt.token" not in str(audit.records)


class TestLogoutAudit:
    async def test_success_records_logout(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.post("/api/v1/auth/logout", json={"refresh_token": "some.refresh.token"})

        assert len(audit.records) == 1
        assert audit.records[0]["event_type"] is AuditEventType.LOGOUT
        assert audit.records[0]["success"] is True


class TestApiKeyAudit:
    async def test_creation_records_api_key_created(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        from querymind.api.dependencies import get_current_user_jwt_only

        fake = FakeAuthenticationService()
        fake.create_api_key_result = make_api_key_created()
        audit = FakeAuditLogger()
        _install(app, fake, audit)
        app.dependency_overrides[get_current_user_jwt_only] = lambda: make_user_read(
            id=3, username="gina"
        )

        response = await client.post("/api/v1/auth/api-keys", json={"name": "CI pipeline"})

        assert response.status_code == 201
        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.API_KEY_CREATED
        assert record["actor_user_id"] == 3
        assert record["actor_username"] == "gina"
        assert "qm_" not in str(record)  # the raw key itself never reaches the audit record

    async def test_revocation_records_api_key_revoked(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        from querymind.api.dependencies import get_current_user_jwt_only

        fake = FakeAuthenticationService()
        audit = FakeAuditLogger()
        _install(app, fake, audit)
        app.dependency_overrides[get_current_user_jwt_only] = lambda: make_user_read(
            id=4, username="hank"
        )

        await client.delete("/api/v1/auth/api-keys/42")

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.API_KEY_REVOKED
        assert record["actor_user_id"] == 4


class TestAuthorizationDeniedAudit:
    async def test_a_403_records_authorization_denied_with_the_actual_caller(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """Uses a real bearer token through the *real* `get_current_user` (not overridden) so
        `request.state.user` is genuinely stashed the way production traffic would -- only
        `AuthenticationServiceDep` is faked, mirroring `test_authorization.py`'s own precedent
        of exercising the real dependency chain, not a wholesale identity override.
        """
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(id=11, username="ivy", role=UserRole.VIEWER)
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        response = await client.get(
            "/api/v1/settings", headers={"Authorization": "Bearer a.valid.token"}
        )

        assert response.status_code == 403
        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["event_type"] is AuditEventType.AUTHORIZATION_DENIED
        assert record["success"] is False
        assert record["actor_user_id"] == 11
        assert record["actor_username"] == "ivy"

    async def test_never_leaks_a_bearer_token_into_an_authorization_denied_record(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(role=UserRole.VIEWER)
        audit = FakeAuditLogger()
        _install(app, fake, audit)

        await client.get(
            "/api/v1/settings",
            headers={"Authorization": "Bearer a-very-real-looking.jwt.token"},
        )

        assert "a-very-real-looking.jwt.token" not in str(audit.records)
