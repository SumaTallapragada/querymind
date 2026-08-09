"""Unit tests for `/api/v1/auth/*`. `AuthenticationServiceDep` is mocked (mirrors
`test_query.py`'s `_FakeEngine`/`get_query_mind_engine` override exactly) -- these tests verify
each route's own, and only, responsibilities: validating the request body, calling the right
`AuthenticationService` method with the right arguments, and mapping its result/exception to the
right HTTP response. `test_auth_integration.py` is what proves the real service (Phase 22A Part
1, unmodified) actually works end to end, against the real database.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_authentication_service
from querymind.auth.exceptions import (
    DuplicateUserError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from tests.api.conftest import FakeAuthenticationService, make_token_pair, make_user_read

_user_read = make_user_read
_token_pair = make_token_pair


def _install(app: FastAPI, fake: FakeAuthenticationService) -> None:
    app.dependency_overrides[get_authentication_service] = lambda: fake


class TestRegister:
    async def test_returns_201_and_the_created_user(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = _user_read()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "password123"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "alice"
        assert "password" not in body
        assert "password_hash" not in body

    async def test_calls_register_user_with_the_request_fields(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = _user_read()
        _install(app, fake)

        await client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.com", "password": "password123"},
        )

        assert fake.register_calls == [
            {"username": "bob", "email": "bob@example.com", "password": "password123"}
        ]

    async def test_a_duplicate_user_returns_409(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.register_user_result = DuplicateUserError("already taken")
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "carol", "email": "carol@example.com", "password": "password123"},
        )

        assert response.status_code == 409
        assert response.json()["error_type"] == "DuplicateUserError"

    async def test_a_malformed_email_is_rejected_before_reaching_the_service(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "dave", "email": "not-an-email", "password": "password123"},
        )

        assert response.status_code == 422
        assert fake.register_calls == []

    async def test_a_too_short_password_is_rejected_before_reaching_the_service(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "erin", "email": "erin@example.com", "password": "short"},
        )

        assert response.status_code == 422
        assert fake.register_calls == []

    async def test_an_unexpected_field_is_rejected(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "frank",
                "email": "frank@example.com",
                "password": "password123",
                "is_superuser": True,
            },
        )

        assert response.status_code == 422
        assert fake.register_calls == []


class TestLogin:
    async def test_returns_200_and_a_token_pair(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = _user_read(id=7)
        fake.create_token_pair_result = _token_pair()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "access.token.value"
        assert body["refresh_token"] == "refresh.token.value"
        assert body["token_type"] == "bearer"

    async def test_authenticates_then_issues_tokens_for_that_user_id(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = _user_read(id=42)
        fake.create_token_pair_result = _token_pair()
        _install(app, fake)

        await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
        )

        assert fake.authenticate_calls == [("alice", "password123")]
        assert fake.create_token_pair_calls == [42]

    async def test_wrong_credentials_return_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("bad credentials")
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "wrong"}
        )

        assert response.status_code == 401
        assert response.json()["error_type"] == "InvalidCredentialsError"
        assert fake.create_token_pair_calls == []

    async def test_an_inactive_account_returns_403(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InactiveUserError("inactive")
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
        )

        assert response.status_code == 403
        assert response.json()["error_type"] == "InactiveUserError"


class TestRefresh:
    async def test_returns_200_and_a_new_token_pair(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = _token_pair()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "some.refresh.token"}
        )

        assert response.status_code == 200
        assert response.json()["access_token"] == "access.token.value"
        assert fake.refresh_tokens_calls == ["some.refresh.token"]

    async def test_a_revoked_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = RefreshTokenRevokedError("revoked")
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "revoked.token"}
        )

        assert response.status_code == 401
        assert response.json()["error_type"] == "RefreshTokenRevokedError"

    async def test_an_expired_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = TokenExpiredError("expired")
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "expired.token"}
        )

        assert response.status_code == 401
        assert response.json()["error_type"] == "TokenExpiredError"

    async def test_an_invalid_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.refresh_tokens_result = InvalidTokenError("invalid")
        _install(app, fake)

        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})

        assert response.status_code == 401
        assert response.json()["error_type"] == "InvalidTokenError"


class TestLogout:
    async def test_returns_204_with_no_body(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)

        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": "some.refresh.token"}
        )

        assert response.status_code == 204
        assert response.content == b""
        assert fake.logout_calls == ["some.refresh.token"]

    async def test_an_invalid_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.logout_exception = InvalidTokenError("invalid")
        _install(app, fake)

        response = await client.post("/api/v1/auth/logout", json={"refresh_token": "garbage"})

        assert response.status_code == 401


class TestMe:
    async def test_returns_the_current_user(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = _user_read(username="ivy")
        _install(app, fake)

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer a.valid.token"}
        )

        assert response.status_code == 200
        assert response.json()["username"] == "ivy"
        assert fake.get_current_user_calls == ["a.valid.token"]

    async def test_no_authorization_header_returns_401(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)

        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated."
        assert fake.get_current_user_calls == []

    async def test_an_invalid_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InvalidTokenError("invalid")
        _install(app, fake)

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer bad.token"}
        )

        assert response.status_code == 401
        assert response.json()["error_type"] == "InvalidTokenError"

    async def test_an_expired_token_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = TokenExpiredError("expired")
        _install(app, fake)

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer expired.token"}
        )

        assert response.status_code == 401
        assert response.json()["error_type"] == "TokenExpiredError"

    async def test_an_inactive_users_token_returns_403(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = InactiveUserError("inactive")
        _install(app, fake)

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer a.valid.token"}
        )

        assert response.status_code == 403
        assert response.json()["error_type"] == "InactiveUserError"

    async def test_never_exposes_a_password_hash(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.get_current_user_result = _user_read()
        _install(app, fake)

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer a.valid.token"}
        )

        serialized = str(response.json()).lower()
        assert "password" not in serialized
