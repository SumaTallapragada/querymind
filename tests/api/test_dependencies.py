"""Unit tests for the Phase 22A Part 2 dependency functions in `querymind.api.dependencies`
(`get_current_user`, `get_optional_current_user`, `get_admin_user`) -- called directly as plain
async functions, with a `FakeAuthenticationService`, rather than through HTTP. `test_auth.py`'s
`TestMe` class already exercises `get_current_user` end to end through `GET /api/v1/auth/me`;
this file covers `get_optional_current_user`/`get_admin_user`, which no current route uses (both
exist as reusable, Phase 22B-facing infrastructure -- see `dependencies.py`'s own docstring),
plus the exact boundary behavior of all three that's easiest to assert directly.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from querymind.api.dependencies import get_admin_user, get_current_user, get_optional_current_user
from querymind.auth.exceptions import InactiveUserError, InvalidTokenError, TokenExpiredError
from tests.api.conftest import FakeAuthenticationService, make_user_read


class TestGetCurrentUser:
    async def test_returns_the_resolved_user_for_a_token(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = make_user_read(username="alice")

        user = await get_current_user(token="a.valid.token", auth_service=fake)  # type: ignore[arg-type]

        assert user.username == "alice"
        assert fake.get_current_user_calls == ["a.valid.token"]

    async def test_raises_401_when_no_token_is_given(self) -> None:
        fake = FakeAuthenticationService()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=None, auth_service=fake)  # type: ignore[arg-type]

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
            await get_current_user(token="bad.token", auth_service=fake)  # type: ignore[arg-type]

    async def test_propagates_a_token_expired_error_unmapped(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = TokenExpiredError("expired")

        with pytest.raises(TokenExpiredError):
            await get_current_user(token="expired.token", auth_service=fake)  # type: ignore[arg-type]

    async def test_propagates_an_inactive_user_error_unmapped(self) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InactiveUserError("inactive")

        with pytest.raises(InactiveUserError):
            await get_current_user(token="a.token", auth_service=fake)  # type: ignore[arg-type]


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
