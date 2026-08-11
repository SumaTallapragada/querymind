"""Unit tests for the Phase 22A Part 2 dependency functions in `querymind.api.dependencies`
(`get_current_user`, `get_optional_current_user`, `get_admin_user`) -- called directly as plain
async functions, with a `FakeAuthenticationService`, rather than through HTTP. `test_auth.py`'s
`TestMe` class already exercises `get_current_user` end to end through `GET /api/v1/auth/me`;
this file covers `get_optional_current_user`/`get_admin_user`, which no current route uses (both
exist as reusable, Phase 22B-facing infrastructure -- see `dependencies.py`'s own docstring),
plus the exact boundary behavior of all three that's easiest to assert directly.

`RequireAdmin`/`RequireAnalyst`/`RequireViewer`/`RequireAnyRole` (Phase 22B) below are tested
the same way: their underlying functions (`get_admin_required_user`, etc.) called directly with
a `CurrentUser`-shaped `UserRead` and a `FakeAuthenticationService` (whose `require_role`/
`require_any_role` delegate to a real `AuthenticationService` -- see that fake's own docstring
in `conftest.py`), never through HTTP -- route-level 403s are `test_diagnostics.py`/
`test_metrics.py`/`test_settings.py`/`test_query.py`/etc.'s job (each now-protected route
already covers its own 200/403 boundary once per file), and end-to-end role enforcement against
a real database is the authorization suite's integration tests.

`get_current_user`/`get_current_user_jwt_only` (Phase 22D) both now take a `request: Request`
parameter (to stash `request.state.user`, see that function's own docstring) -- `_request()`
below builds a minimal, real `starlette.requests.Request` for these direct calls, the same way
every other parameter here is a minimal stand-in for what FastAPI would otherwise inject.
`get_current_user` additionally takes an `audit_logger` (Phase 22D), which every call below
satisfies with `FakeAuditLogger()` (`conftest.py`) -- a real `AuditLogger` needs a real database
via `AuditRepository`, which these are deliberately *not* -- pure unit tests, no I/O.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from querymind.api.dependencies import (
    RequireAnyRole,
    get_admin_required_user,
    get_admin_user,
    get_analyst_required_user,
    get_current_user,
    get_current_user_jwt_only,
    get_optional_current_user,
    get_viewer_required_user,
)
from querymind.auth.exceptions import (
    ForbiddenRoleError,
    InactiveUserError,
    InsufficientPermissionsError,
    InvalidApiKeyError,
    InvalidTokenError,
    TokenExpiredError,
)
from querymind.auth.models import UserRole
from querymind.security.audit import AuditEventType
from tests.api.conftest import FakeAuditLogger, FakeAuthenticationService, make_user_read


class _StubSettings:
    trust_proxy_headers = False


class _StubAppState:
    settings = _StubSettings()


class _StubApp:
    state = _StubAppState()


def _request() -> Request:
    """A minimal, real `starlette.requests.Request` -- includes a stub `app.state.settings` so
    `get_current_user`'s `_trust_proxy` lookup (Phase 22D) works the same as it would for a real
    request, without constructing a real `Settings()`/needing a real environment.
    """
    return Request(
        scope={"type": "http", "headers": [], "method": "GET", "path": "/", "app": _StubApp()}
    )


class TestGetCurrentUser:
    async def test_returns_the_resolved_user_for_a_token(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(username="alice")

        user = await get_current_user(
            request=_request(),
            token="a.valid.token",
            api_key=None,
            auth_service=fake,  # type: ignore[arg-type]
            audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
        )

        assert user.username == "alice"
        assert fake.get_current_user_calls == ["a.valid.token"]

    async def test_raises_401_when_no_token_or_key_is_given(self) -> None:
        fake = FakeAuthenticationService()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=_request(),
                token=None,
                api_key=None,
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"
        assert fake.get_current_user_calls == []

    async def test_propagates_an_invalid_token_error_unmapped(self) -> None:
        # Not caught here -- querymind.api.exception_handlers maps it to a status code; see
        # test_auth.py::TestMe for the HTTP-level (401) assertion of the same behavior.
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InvalidTokenError("bad token")

        with pytest.raises(InvalidTokenError):
            await get_current_user(
                request=_request(),
                token="bad.token",
                api_key=None,
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
            )

    async def test_propagates_a_token_expired_error_unmapped(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = TokenExpiredError("expired")

        with pytest.raises(TokenExpiredError):
            await get_current_user(
                request=_request(),
                token="expired.token",
                api_key=None,
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
            )

    async def test_propagates_an_inactive_user_error_unmapped(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InactiveUserError("inactive")

        with pytest.raises(InactiveUserError):
            await get_current_user(
                request=_request(),
                token="a.token",
                api_key=None,
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
            )

    async def test_stashes_the_resolved_user_on_request_state(self) -> None:
        fake = FakeAuthenticationService()
        resolved = make_user_read(username="stashed")
        fake.get_current_user_result = resolved
        request = _request()

        await get_current_user(
            request=request,
            token="a.valid.token",
            api_key=None,
            auth_service=fake,  # type: ignore[arg-type]
            audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
        )

        assert request.state.user is resolved

    async def test_an_api_key_resolves_via_authenticate_api_key_not_the_jwt_path(self) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = make_user_read(username="key_user")
        audit_logger = FakeAuditLogger()

        user = await get_current_user(
            request=_request(),
            token=None,
            api_key="qm_some-key",
            auth_service=fake,  # type: ignore[arg-type]
            audit_logger=audit_logger,  # type: ignore[arg-type]
        )

        assert user.username == "key_user"
        assert fake.authenticate_api_key_calls == ["qm_some-key"]
        assert fake.get_current_user_calls == []
        assert len(audit_logger.records) == 1
        assert audit_logger.records[0]["event_type"] is AuditEventType.API_KEY_AUTH_SUCCESS
        assert audit_logger.records[0]["success"] is True
        assert audit_logger.records[0]["actor_username"] == "key_user"

    async def test_an_api_key_takes_precedence_when_both_are_somehow_present(self) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = make_user_read(username="key_user")
        fake.get_current_user_result = make_user_read(username="jwt_user")

        user = await get_current_user(
            request=_request(),
            token="a.valid.token",
            api_key="qm_some-key",
            auth_service=fake,  # type: ignore[arg-type]
            audit_logger=FakeAuditLogger(),  # type: ignore[arg-type]
        )

        assert user.username == "key_user"
        assert fake.get_current_user_calls == []

    async def test_propagates_an_invalid_api_key_error_unmapped(self) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = InvalidApiKeyError("bad key")
        audit_logger = FakeAuditLogger()

        with pytest.raises(InvalidApiKeyError):
            await get_current_user(
                request=_request(),
                token=None,
                api_key="qm_bad-key",
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=audit_logger,  # type: ignore[arg-type]
            )

        assert len(audit_logger.records) == 1
        assert audit_logger.records[0]["event_type"] is AuditEventType.API_KEY_AUTH_FAILURE
        assert audit_logger.records[0]["success"] is False

    async def test_an_audit_failure_record_never_contains_the_raw_api_key(self) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = InvalidApiKeyError("bad key")
        audit_logger = FakeAuditLogger()

        with pytest.raises(InvalidApiKeyError):
            await get_current_user(
                request=_request(),
                token=None,
                api_key="qm_a-real-looking-secret-value",
                auth_service=fake,  # type: ignore[arg-type]
                audit_logger=audit_logger,  # type: ignore[arg-type]
            )

        assert "qm_a-real-looking-secret-value" not in str(audit_logger.records)


class TestGetCurrentUserJwtOnly:
    """`CurrentUserJwtOnly`'s underlying function -- the `/auth/api-keys*` management routes'
    identity dependency. Never consults an API key at all; see its own docstring.
    """

    async def test_returns_the_resolved_user_for_a_token(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(username="alice")

        user = await get_current_user_jwt_only(
            request=_request(),
            token="a.valid.token",
            auth_service=fake,  # type: ignore[arg-type]
        )

        assert user.username == "alice"

    async def test_raises_401_when_no_token_is_given(self) -> None:
        fake = FakeAuthenticationService()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_jwt_only(
                request=_request(),
                token=None,
                auth_service=fake,  # type: ignore[arg-type]
            )

        assert exc_info.value.status_code == 401

    async def test_stashes_the_resolved_user_on_request_state(self) -> None:
        fake = FakeAuthenticationService()
        resolved = make_user_read(username="stashed")
        fake.get_current_user_result = resolved
        request = _request()

        await get_current_user_jwt_only(request=request, token="a.valid.token", auth_service=fake)  # type: ignore[arg-type]

        assert request.state.user is resolved


class TestGetOptionalCurrentUser:
    async def test_returns_none_when_no_token_is_given(self) -> None:
        fake = FakeAuthenticationService()

        user = await get_optional_current_user(token=None, auth_service=fake)  # type: ignore[arg-type]

        assert user is None
        assert fake.get_current_user_calls == []

    async def test_returns_the_resolved_user_for_a_valid_token(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(username="bob")

        user = await get_optional_current_user(token="a.valid.token", auth_service=fake)  # type: ignore[arg-type]

        assert user is not None
        assert user.username == "bob"

    async def test_a_present_but_invalid_token_still_raises_rather_than_degrading_to_anonymous(
        self,
    ) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InvalidTokenError("bad token")

        with pytest.raises(InvalidTokenError):
            await get_optional_current_user(token="bad.token", auth_service=fake)  # type: ignore[arg-type]


class TestGetAdminUser:
    async def test_a_superuser_is_returned_unchanged(self) -> None:
        admin = make_user_read(is_superuser=True)

        result = await get_admin_user(user=admin)

        assert result is admin

    async def test_a_non_superuser_raises_403(self) -> None:
        regular_user = make_user_read(is_superuser=False)

        with pytest.raises(HTTPException) as exc_info:
            await get_admin_user(user=regular_user)

        assert exc_info.value.status_code == 403


class TestGetAdminRequiredUser:
    """`RequireAdmin`'s underlying function -- ranked, so only `ADMIN` itself satisfies it."""

    async def test_an_admin_is_returned_unchanged(self) -> None:
        fake = FakeAuthenticationService()
        admin = make_user_read(role=UserRole.ADMIN)

        result = await get_admin_required_user(user=admin, auth_service=fake)  # type: ignore[arg-type]

        assert result is admin

    async def test_an_analyst_raises_forbidden_role_error(self) -> None:
        fake = FakeAuthenticationService()
        analyst = make_user_read(role=UserRole.ANALYST)

        with pytest.raises(ForbiddenRoleError):
            await get_admin_required_user(user=analyst, auth_service=fake)  # type: ignore[arg-type]

    async def test_a_viewer_raises_forbidden_role_error(self) -> None:
        fake = FakeAuthenticationService()
        viewer = make_user_read(role=UserRole.VIEWER)

        with pytest.raises(ForbiddenRoleError):
            await get_admin_required_user(user=viewer, auth_service=fake)  # type: ignore[arg-type]


class TestGetAnalystRequiredUser:
    """`RequireAnalyst`'s underlying function -- ranked, so `ADMIN` satisfies it too."""

    async def test_an_analyst_is_returned_unchanged(self) -> None:
        fake = FakeAuthenticationService()
        analyst = make_user_read(role=UserRole.ANALYST)

        result = await get_analyst_required_user(user=analyst, auth_service=fake)  # type: ignore[arg-type]

        assert result is analyst

    async def test_an_admin_also_satisfies_it(self) -> None:
        fake = FakeAuthenticationService()
        admin = make_user_read(role=UserRole.ADMIN)

        result = await get_analyst_required_user(user=admin, auth_service=fake)  # type: ignore[arg-type]

        assert result is admin

    async def test_a_viewer_raises_forbidden_role_error(self) -> None:
        fake = FakeAuthenticationService()
        viewer = make_user_read(role=UserRole.VIEWER)

        with pytest.raises(ForbiddenRoleError):
            await get_analyst_required_user(user=viewer, auth_service=fake)  # type: ignore[arg-type]


class TestGetViewerRequiredUser:
    """`RequireViewer`'s underlying function -- the floor rank, so every role satisfies it."""

    async def test_a_viewer_is_returned_unchanged(self) -> None:
        fake = FakeAuthenticationService()
        viewer = make_user_read(role=UserRole.VIEWER)

        result = await get_viewer_required_user(user=viewer, auth_service=fake)  # type: ignore[arg-type]

        assert result is viewer

    async def test_an_analyst_also_satisfies_it(self) -> None:
        fake = FakeAuthenticationService()
        analyst = make_user_read(role=UserRole.ANALYST)

        result = await get_viewer_required_user(user=analyst, auth_service=fake)  # type: ignore[arg-type]

        assert result is analyst

    async def test_an_admin_also_satisfies_it(self) -> None:
        fake = FakeAuthenticationService()
        admin = make_user_read(role=UserRole.ADMIN)

        result = await get_viewer_required_user(user=admin, auth_service=fake)  # type: ignore[arg-type]

        assert result is admin


class TestRequireAnyRole:
    """`RequireAnyRole(...)` is a `Depends()` factory, not a plain function -- these tests call
    the inner check function it wraps (`.dependency`) directly, the same as every other
    dependency in this file.
    """

    async def test_a_role_in_the_set_is_returned_unchanged(self) -> None:
        fake = FakeAuthenticationService()
        viewer = make_user_read(role=UserRole.VIEWER)
        check = RequireAnyRole(UserRole.ADMIN, UserRole.VIEWER).dependency

        result = await check(user=viewer, auth_service=fake)  # type: ignore[arg-type]

        assert result is viewer

    async def test_not_hierarchical_a_higher_rank_outside_the_set_still_raises(self) -> None:
        """An `ADMIN` does not automatically satisfy `RequireAnyRole(VIEWER)` -- unlike
        `RequireAdmin`/`RequireAnalyst`/`RequireViewer`, this is exact-set membership, not rank.
        """
        fake = FakeAuthenticationService()
        admin = make_user_read(role=UserRole.ADMIN)
        check = RequireAnyRole(UserRole.VIEWER).dependency

        with pytest.raises(InsufficientPermissionsError):
            await check(user=admin, auth_service=fake)  # type: ignore[arg-type]

    async def test_a_role_outside_the_set_raises_insufficient_permissions_error(self) -> None:
        fake = FakeAuthenticationService()
        analyst = make_user_read(role=UserRole.ANALYST)
        check = RequireAnyRole(UserRole.ADMIN, UserRole.VIEWER).dependency

        with pytest.raises(InsufficientPermissionsError):
            await check(user=analyst, auth_service=fake)  # type: ignore[arg-type]
