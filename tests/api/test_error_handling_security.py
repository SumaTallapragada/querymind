"""Phase 22D-5: verifies the API's error handling is secure, consistent, and never leaks
sensitive information -- not a new architecture, a proof that the one built across 22A-22D
(`querymind.api.exception_handlers`'s `_STATUS_BY_EXCEPTION` mapping, `querymind.security.audit`,
`querymind.security.rate_limiter`) already behaves correctly, plus regression coverage for the
two genuine gaps this phase's verification found (see the two classes below whose names start
with `TestValidationErrorsNeverEchoSecrets`/`TestUnexpectedExceptionReturns500WithNoLeak` for the
production fixes each locks in).

Deliberately does not re-prove what's already covered elsewhere:
- `tests/api/test_auth.py`/`test_api_keys.py`/`test_authorization.py` already exercise every
  mapped exception's HTTP status one route at a time -- this file adds only the HTTP-level gaps
  those files leave (API-key 401s via a route, not just `test_dependencies.py`'s direct calls;
  an unmapped 500; validation-error echoing).
- `tests/api/test_rate_limiting.py::TestNoInformationLeakageIn429Responses` already proves the
  429 contract (shape, generic detail, positive `Retry-After`, no bucket/capacity/identity
  leakage) -- not duplicated here.
- `tests/api/test_audit_logging.py` already proves login/register/refresh/authorization-denied
  audit success+failure and that none of them leak a password/token -- this file adds only the
  one HTTP-level gap it leaves (API-key auth failure's audit record, only unit-tested directly in
  `test_dependencies.py` today).

Sentinel values (`TEST_PASSWORD_SECRET`, `TEST_ACCESS_TOKEN_SECRET`, `TEST_REFRESH_TOKEN_SECRET`,
`TEST_RAW_API_KEY_SECRET`, `TEST_DB_PASSWORD_SECRET`) are used throughout instead of realistic-
looking values, per this phase's explicit instruction -- never a real credential in a test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from querymind.api.app import create_app
from querymind.api.dependencies import (
    get_audit_logger,
    get_authentication_service,
    get_current_user,
)
from querymind.auth.exceptions import (
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    ForbiddenRoleError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from querymind.auth.models import UserRole
from querymind.core.config import Settings
from querymind.security.audit import AuditEventType
from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.exceptions import DatabaseConnectionError
from tests.api.conftest import FakeAuditLogger, FakeAuthenticationService, make_user_read

_PASSWORD_SECRET = "TEST_PASSWORD_SECRET"
_ACCESS_TOKEN_SECRET = "TEST_ACCESS_TOKEN_SECRET"
_REFRESH_TOKEN_SECRET = "TEST_REFRESH_TOKEN_SECRET"
_RAW_API_KEY_SECRET = "TEST_RAW_API_KEY_SECRET"
_DB_PASSWORD_SECRET = "TEST_DB_PASSWORD_SECRET"

_FORBIDDEN_403_SUBSTRINGS = (
    "Traceback",
    "traceback",
    '.py"',
    "line ",
    "sqlalchemy",
    "asyncpg",
    "site-packages",
    "get_admin_required_user",
    "Depends",
    "querymind.api",
)


def _settings(**overrides: Any) -> Settings:
    return Settings(
        postgres_user="test",
        postgres_password="test",  # type: ignore[arg-type]
        postgres_db="test",
        postgres_host="localhost",
        log_format="console",
        **overrides,
    )


@asynccontextmanager
async def _client(settings: Settings) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    """`raise_app_exceptions=False`, unlike every other file's own `_client()` helper (e.g.
    `test_rate_limiting.py`'s) -- those never deliberately trigger a genuinely unmapped
    exception, so httpx's default (re-raise it to the caller, for debugging) never matters. This
    file's whole point is to observe the *actual HTTP response* `ServerErrorMiddleware` sends for
    exactly that case (see `TestUnexpectedExceptionReturns500WithNoLeak`); without this, httpx
    re-raises the original exception into the test itself instead of returning the response.
    """
    app = create_app(settings=settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac


def _install_audit(app: FastAPI, fake: FakeAuthenticationService, audit: FakeAuditLogger) -> None:
    """Mirrors `test_audit_logging.py`'s own `_install` -- the failure half of audit logging
    (`querymind.api.exception_handlers`) reads `app.state.container.audit_logger` directly, not
    through `Depends()`, so the frozen container needs the same `object.__setattr__` escape
    hatch that file's own docstring explains.
    """
    app.dependency_overrides[get_authentication_service] = lambda: fake
    app.dependency_overrides[get_audit_logger] = lambda: audit
    object.__setattr__(app.state.container, "audit_logger", audit)


class TestSecretsNeverLeakInAuthFailureResponses:
    """Every kind of authentication failure this API can produce, each with a sentinel secret
    embedded in the attempted credential -- the sentinel must never surface in the response body.
    """

    async def test_a_wrong_password_never_appears_in_the_401_body(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("bad credentials")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": _PASSWORD_SECRET}
        )

        assert response.status_code == 401
        assert _PASSWORD_SECRET not in response.text

    async def test_a_bad_refresh_token_never_appears_in_the_401_body(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = InvalidTokenError("bad token")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": _REFRESH_TOKEN_SECRET}
        )

        assert response.status_code == 401
        assert _REFRESH_TOKEN_SECRET not in response.text

    async def test_a_bad_access_token_never_appears_in_the_401_body(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InvalidTokenError("bad token")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {_ACCESS_TOKEN_SECRET}"}
        )

        assert response.status_code == 401
        assert _ACCESS_TOKEN_SECRET not in response.text

    async def test_a_bad_api_key_never_appears_in_the_401_body(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = InvalidApiKeyError("bad key")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get(
            "/api/v1/auth/me", headers={"X-API-Key": f"qm_{_RAW_API_KEY_SECRET}"}
        )

        assert response.status_code == 401
        assert _RAW_API_KEY_SECRET not in response.text

    async def test_the_authorization_header_value_itself_never_appears_in_any_body(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """Not just the *token*, but the raw header value a caller sent -- proven with a
        deliberately malformed scheme (not even `Bearer`), which FastAPI's own `auto_error=False`
        extraction treats as "no token," so `get_current_user` raises its own 401 directly.
        """
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Basic {_ACCESS_TOKEN_SECRET}"},
        )

        assert response.status_code == 401
        assert _ACCESS_TOKEN_SECRET not in response.text


class TestApiKeyAuthenticationHttpStatuses:
    """`InvalidApiKeyError`/`ApiKeyExpiredError`/`ApiKeyRevokedError` (Phase 22D) at the HTTP
    layer, through a real route (`GET /auth/me`) -- `test_dependencies.py` already proves
    `get_current_user` propagates each unmapped; this proves the mapping to its actual status
    code and `error_type` end to end.
    """

    async def test_an_invalid_key_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = InvalidApiKeyError("not recognized")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get("/api/v1/auth/me", headers={"X-API-Key": "qm_bad"})

        assert response.status_code == 401
        assert response.json()["error_type"] == "InvalidApiKeyError"

    async def test_an_expired_key_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = ApiKeyExpiredError("expired")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get("/api/v1/auth/me", headers={"X-API-Key": "qm_expired"})

        assert response.status_code == 401
        assert response.json()["error_type"] == "ApiKeyExpiredError"

    async def test_a_revoked_key_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = ApiKeyRevokedError("revoked")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get("/api/v1/auth/me", headers={"X-API-Key": "qm_revoked"})

        assert response.status_code == 401
        assert response.json()["error_type"] == "ApiKeyRevokedError"


class TestCredentialEnumerationIsPrevented:
    """An unknown username and a known username with the wrong password must be genuinely
    indistinguishable -- both routes through the same `InvalidCredentialsError` (see that
    exception's own docstring), but this proves the *HTTP response* carries no discriminating
    detail either, not just that the exception type is shared.
    """

    async def test_an_unknown_username_and_a_wrong_password_yield_identical_responses(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("Incorrect username/email or password.")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        unknown_user_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "no-such-user", "password": "whatever123"},
        )
        wrong_password_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "a-real-user", "password": "wrong-password"},
        )

        assert unknown_user_response.status_code == wrong_password_response.status_code == 401
        assert unknown_user_response.json() == wrong_password_response.json()


class TestAuthorizationDenialNeverLeaksInternals:
    """A `403` from `require_role`/`require_any_role` must carry only the standard
    `detail`/`error_type` envelope -- no dependency name, no stack trace, no database detail, and
    no more about the RBAC implementation than the role names already visible to the caller
    (their own role, and the rank they were missing) -- see `AuthenticationService.require_role`'s
    own docstring for why that much is the *intended* user-facing message, not a leak.
    """

    async def test_the_body_has_only_the_standard_error_shape(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)

        response = await client.get("/api/v1/settings")

        assert response.status_code == 403
        assert set(response.json().keys()) == {"detail", "error_type"}
        assert response.json()["error_type"] == "ForbiddenRoleError"

    @pytest.mark.parametrize("forbidden", _FORBIDDEN_403_SUBSTRINGS)
    async def test_the_body_never_contains_implementation_internals(
        self, app: FastAPI, client: AsyncClient, forbidden: str
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)

        response = await client.get("/api/v1/health/diagnostics")

        assert forbidden not in response.text

    async def test_the_message_reveals_only_the_two_role_names_already_known_to_the_caller(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)

        response = await client.get("/api/v1/health/metrics")

        detail = response.json()["detail"]
        assert ForbiddenRoleError.__name__ != detail  # sanity: detail is the message, not the type
        assert "viewer" in detail.lower()
        assert "admin" in detail.lower()  # /health/metrics requires ADMIN -- test_authorization.py


class TestUnexpectedExceptionReturns500WithNoLeak:
    """The generic `Exception` safety net (`querymind.api.app.unhandled_exception_handler`) --
    exercised two ways: a bare, unmapped exception raised from inside a dependency, and a real
    unreachable-database failure through `GET /health/ready` (`querymind.db.session
    .transactional_session` re-raises unchanged; nothing maps `DatabaseConnectionError`-style
    translation onto a plain SQLAlchemy session, so this is the *un*mapped path, not the
    `sql_execution` engine's own 503 -- see `TestDatabaseConnectionFailureNeverLeaksCredentials`
    below for that one).

    Both use an explicit `app_debug=False` `Settings` -- never the ambient one -- because this
    phase's own verification found the *shipped* `.env`/`.env.example` default was `APP_DEBUG=
    true`, which makes Starlette's `ServerErrorMiddleware` return a full Python traceback (real
    file paths, the real driver exception, real module internals) as the response body,
    completely bypassing this safety net regardless of anything in `querymind.api.app` itself --
    fixed in `.env.example` as part of this phase (see the final report). `test_settings.py`
    below is the one hermetic, `.env`-independent regression lock for the *shipped default*
    specifically; these two prove the *safety net itself* is correct once that default holds.
    """

    async def test_settings_field_default_is_the_safe_one(self) -> None:
        """`Settings.app_debug`'s own `Field(default=...)` -- not an instance built from `.env`,
        which would depend on whatever this machine's own `.env` happens to contain (a real gap
        this phase's investigation surfaced: `Settings(...)` falls back to `.env` for any field
        not passed explicitly, so an ordinary `Settings()` in a checkout with a debug-enabled
        `.env` is *not* actually hermetic for this field). Reading the field's declared default
        directly is the one assertion that's independent of whatever `.env` exists on disk.
        """
        assert Settings.model_fields["app_debug"].default is False

    async def test_an_unmapped_exception_from_a_dependency_returns_a_generic_500(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = RuntimeError(f"internal detail: {_ACCESS_TOKEN_SECRET}")

        async with _client(_settings(app_debug=False)) as (app, client):
            app.dependency_overrides[get_authentication_service] = lambda: fake

            response = await client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer a.token"}
            )

            assert response.status_code == 500
            assert response.json() == {"detail": "Internal server error"}
            assert _ACCESS_TOKEN_SECRET not in response.text
            assert "RuntimeError" not in response.text
            assert "Traceback" not in response.text

    async def test_a_real_unreachable_database_returns_a_generic_500_via_health_ready(
        self,
    ) -> None:
        """`GET /health/ready` (`querymind.api.v1.endpoints.health`) never catches its own
        session's exception -- a real connection failure propagates all the way to the generic
        safety net, unmapped, exactly like any other genuinely unexpected error.
        """
        sentinel_settings = Settings(
            postgres_user="test",
            postgres_password=_DB_PASSWORD_SECRET,  # type: ignore[arg-type]
            postgres_db="test",
            postgres_host="localhost",
            log_format="console",
            app_debug=False,
        )
        async with _client(sentinel_settings) as (_, client):
            response = await client.get("/api/v1/health/ready")

            assert response.status_code == 500
            assert response.json() == {"detail": "Internal server error"}
            assert _DB_PASSWORD_SECRET not in response.text
            assert "Traceback" not in response.text
            assert "asyncpg" not in response.text
            assert "sqlalchemy" not in response.text.lower()


class TestDatabaseConnectionFailureNeverLeaksCredentials:
    """`querymind.sql_execution.connection.DatabaseConnectionProvider.acquire` deliberately keeps
    a real driver failure's own message (`DatabaseConnectionError(str(exc))`, mapped to a client-
    visible `503` by `querymind.api.exception_handlers`) rather than a hand-written generic one --
    unlike the safety net above, this is a genuinely informative error a caller may want (e.g.
    distinguishing "the database is down" from other 500s). This proves that choice is still
    safe empirically, against the real driver, rather than assuming a raw exception message never
    contains a credential: mirrors `tests/sql_execution/test_connection.py::TestAcquireFailure`'s
    own pattern (a real `AsyncEngine` pointed at a deliberately bad target), against the real,
    already-running local Postgres so a genuine `asyncpg` auth failure is what's actually raised.
    """

    async def test_a_wrong_password_error_never_contains_the_attempted_password(
        self, real_settings: Settings
    ) -> None:
        bad_engine = create_async_engine(
            f"postgresql+asyncpg://{real_settings.postgres_user}:{_DB_PASSWORD_SECRET}"
            f"@{real_settings.postgres_host}:{real_settings.postgres_port}"
            f"/{real_settings.postgres_db}"
        )
        provider = DatabaseConnectionProvider(bad_engine)
        try:
            with pytest.raises(DatabaseConnectionError) as exc_info:
                async with provider.acquire():
                    pass
            assert _DB_PASSWORD_SECRET not in str(exc_info.value)
            assert real_settings.postgres_password.get_secret_value() not in str(exc_info.value)
        finally:
            await bad_engine.dispose()


class TestValidationErrorsNeverEchoSecrets:
    """`querymind.api.exception_handlers._handle_validation_error` (added this phase): FastAPI's
    own default `RequestValidationError` handler includes the exact submitted value for every
    failed field (Pydantic v2's `input` key) -- harmless for `username`/`email`/`question`, a real
    leak for `password`/`refresh_token`/`raw_key`/etc. This class proves the fix (secrets no
    longer echoed) and, just as importantly, the control case (ordinary fields still are --
    proving the fix is scoped, not a blanket regression that would make every `422` less useful).
    """

    async def test_a_too_short_password_is_never_echoed_back(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "erin",
                "email": "erin@example.com",
                "password": _PASSWORD_SECRET[:5],
            },
        )

        assert response.status_code == 422
        assert _PASSWORD_SECRET[:5] not in response.text
        errors = response.json()["detail"]
        (password_error,) = (e for e in errors if e["loc"][-1] == "password")
        assert "input" not in password_error
        assert password_error["msg"]  # the field/reason is still reported

    async def test_a_wrong_type_refresh_token_is_never_echoed_back(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": {"nested": _REFRESH_TOKEN_SECRET}}
        )

        assert response.status_code == 422
        assert _REFRESH_TOKEN_SECRET not in response.text

    async def test_meanwhile_an_ordinary_field_is_still_echoed_for_debuggability(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "x", "email": "not-an-email", "password": "password123"},
        )

        assert response.status_code == 422
        errors = response.json()["detail"]
        (username_error,) = (e for e in errors if e["loc"][-1] == "username")
        assert username_error["input"] == "x"


class TestApiKeyAuthFailureAuditAtHttpLevel:
    """`test_dependencies.py::TestGetCurrentUser.test_an_audit_failure_record_never_contains_
    the_raw_api_key` already proves this at the direct-call level; this is the same guarantee
    through a real route, matching `test_audit_logging.py`'s own HTTP-level style for every other
    audited event.
    """

    async def test_records_api_key_auth_failure_without_leaking_the_key(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = InvalidApiKeyError("bad key")
        audit = FakeAuditLogger()
        _install_audit(app, fake, audit)

        response = await client.get(
            "/api/v1/auth/me", headers={"X-API-Key": f"qm_{_RAW_API_KEY_SECRET}"}
        )

        assert response.status_code == 401
        assert len(audit.records) == 1
        assert audit.records[0]["event_type"] is AuditEventType.API_KEY_AUTH_FAILURE
        assert audit.records[0]["success"] is False
        assert _RAW_API_KEY_SECRET not in str(audit.records)


class TestErrorResponseMatrixConsistency:
    """Section 10's matrix: every mapped status this API produces carries exactly
    `{"detail", "error_type"}` -- nothing more, nothing less. `422` (a list of field errors, not
    one exception) and the unmapped `500` safety net (deliberately `{"detail"}` only -- see
    `querymind.api.app`'s own docstring on why that one stays a fixed safety net, not a mapped
    exception) are structurally different by design and are proven separately above/elsewhere,
    not folded into this table.
    """

    async def test_no_authentication_returns_401_with_no_error_type_field(
        self, client: AsyncClient
    ) -> None:
        """The one 401 that isn't a mapped `AuthenticationError` at all -- raised directly by
        `get_current_user`/`get_current_user_jwt_only` as a plain `HTTPException` for "no
        credential was even given" -- so its body is FastAPI's own `{"detail": ...}` shape, with
        no `error_type` key, which is correct and already covered by `test_auth.py::TestMe
        ::test_no_authorization_header_returns_401`; kept here only as a note, not a duplicate
        assertion.
        """
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert "error_type" not in response.json()

    @pytest.mark.parametrize(
        ("exc", "expected_status"),
        [
            pytest.param(InvalidCredentialsError("bad"), 401, id="bad_credentials"),
            pytest.param(InvalidApiKeyError("bad"), 401, id="invalid_api_key"),
            pytest.param(ApiKeyExpiredError("expired"), 401, id="expired_api_key"),
            pytest.param(ApiKeyRevokedError("revoked"), 401, id="revoked_api_key"),
        ],
    )
    async def test_every_mapped_api_key_and_credential_failure_has_the_standard_shape(
        self, app: FastAPI, client: AsyncClient, exc: Exception, expected_status: int
    ) -> None:
        fake = FakeAuthenticationService()
        if isinstance(exc, InvalidCredentialsError):
            fake.authenticate_result = exc
            app.dependency_overrides[get_authentication_service] = lambda: fake
            response = await client.post(
                "/api/v1/auth/login", json={"username": "a", "password": "b"}
            )
        else:
            fake.authenticate_api_key_result = exc
            app.dependency_overrides[get_authentication_service] = lambda: fake
            response = await client.get("/api/v1/auth/me", headers={"X-API-Key": "qm_x"})

        assert response.status_code == expected_status
        assert set(response.json().keys()) == {"detail", "error_type"}
        assert response.json()["error_type"] == type(exc).__name__

    async def test_insufficient_role_is_403_with_the_standard_shape(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)

        response = await client.get("/api/v1/settings")

        assert response.status_code == 403
        assert set(response.json().keys()) == {"detail", "error_type"}

    async def test_validation_failure_is_422_with_a_list_shaped_detail(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/api/v1/auth/register", json={"username": "x"})

        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
