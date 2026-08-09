"""End-to-end tests against the real, fully wired authentication stack, through HTTP.

Uses `real_settings` (the actual, already-running local Postgres instance) and no mocking at
all -- mirrors `test_execution.py`'s own "no LLM in this path, so nothing needs mocking"
precedent exactly; `AuthenticationService` never touches the LLM either. Where `tests/auth/
test_integration.py` (Phase 22A Part 1) proves the service and repository work end to end
against real Postgres, this file proves the same thing one layer up: through real HTTP requests,
real request/response (de)serialization, and the real `querymind.api.exception_handlers`/
`CurrentUser` wiring this phase adds.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.api.app import create_app
from querymind.auth.models import RefreshToken, User
from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory


@pytest.fixture
async def real_client(real_settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=real_settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture(autouse=True)
async def _clean_auth_tables(real_settings: Settings) -> AsyncIterator[None]:
    """Module-local (not in `tests/api/conftest.py`), mirroring `tests/auth/test_integration.py`'s
    identical fixture -- only this file's tests touch `users`/`refresh_tokens`.
    """
    yield
    engine = create_engine(real_settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)
    async with session_factory() as session:
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()
    await engine.dispose()


async def _register(client: AsyncClient, username: str, password: str = "password123") -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert response.status_code == 201, response.text


async def _login(
    client: AsyncClient, username: str, password: str = "password123"
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    tokens: dict[str, str] = response.json()
    return tokens


class TestRegistrationAndLogin:
    async def test_a_registered_user_can_log_in(self, real_client: AsyncClient) -> None:
        await _register(real_client, "alice")

        tokens = await _login(real_client, "alice")

        assert tokens["access_token"]
        assert tokens["refresh_token"]
        assert tokens["token_type"] == "bearer"

    async def test_login_fails_with_the_wrong_password(self, real_client: AsyncClient) -> None:
        await _register(real_client, "bob")

        response = await real_client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": "wrong-password"}
        )

        assert response.status_code == 401

    async def test_registering_the_same_username_twice_returns_409(
        self, real_client: AsyncClient
    ) -> None:
        await _register(real_client, "carol")

        response = await real_client.post(
            "/api/v1/auth/register",
            json={"username": "carol", "email": "carol2@example.com", "password": "password123"},
        )

        assert response.status_code == 409

    async def test_the_password_is_never_returned_anywhere(self, real_client: AsyncClient) -> None:
        response = await real_client.post(
            "/api/v1/auth/register",
            json={"username": "dave", "email": "dave@example.com", "password": "a-real-password"},
        )

        serialized = str(response.json()).lower()
        assert "a-real-password" not in serialized
        assert "password_hash" not in serialized


class TestMe:
    async def test_returns_the_authenticated_user(self, real_client: AsyncClient) -> None:
        await _register(real_client, "erin")
        tokens = await _login(real_client, "erin")

        response = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "erin"
        assert body["email"] == "erin@example.com"

    async def test_without_a_token_returns_401(self, real_client: AsyncClient) -> None:
        response = await real_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_with_a_malformed_token_returns_401(self, real_client: AsyncClient) -> None:
        response = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        assert response.status_code == 401

    async def test_a_refresh_token_presented_as_an_access_token_is_rejected(
        self, real_client: AsyncClient
    ) -> None:
        await _register(real_client, "frank")
        tokens = await _login(real_client, "frank")

        response = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
        )

        assert response.status_code == 401


class TestFullLifecycle:
    """register -> login -> me -> refresh (rotate) -> me with the new token -> logout ->
    the old and new refresh tokens are both now unusable, against real Postgres and real HTTP.
    """

    async def test_the_complete_lifecycle(self, real_client: AsyncClient) -> None:
        await _register(real_client, "gina")
        tokens = await _login(real_client, "gina")

        me_response = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "gina"

        refresh_response = await real_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh_response.status_code == 200
        rotated = refresh_response.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

        me_again = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"}
        )
        assert me_again.status_code == 200

        reuse_old_refresh = await real_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert reuse_old_refresh.status_code == 401

        logout_response = await real_client.post(
            "/api/v1/auth/logout", json={"refresh_token": rotated["refresh_token"]}
        )
        assert logout_response.status_code == 204

        refresh_after_logout = await real_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert refresh_after_logout.status_code == 401

    async def test_logging_out_does_not_invalidate_the_still_valid_access_token(
        self, real_client: AsyncClient
    ) -> None:
        await _register(real_client, "hank")
        tokens = await _login(real_client, "hank")

        await real_client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

        response = await real_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert response.status_code == 200
