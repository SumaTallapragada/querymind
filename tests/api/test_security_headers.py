"""Tests for `querymind.api.middleware.SecurityHeadersMiddleware` (Phase 22D).

`app`/`client` (from `tests/api/conftest.py`) use the shared hermetic `Settings`, whose
`app_env` defaults to `"development"` -- exactly what's needed to prove HSTS stays absent by
default. The one production-HSTS test below builds its own app from a `Settings` instance with
`app_env="production"`, mirroring `tests/api/test_rate_limiting.py`'s own `_settings()`/`_client()`
helper pattern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.api.dependencies import get_authentication_service, get_current_user
from querymind.auth.exceptions import InvalidCredentialsError
from querymind.core.config import Settings
from tests.api.conftest import FakeAuthenticationService, make_user_read


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
    app = create_app(settings=settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac


class TestBaselineHeaders:
    async def test_x_content_type_options_is_present(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    async def test_referrer_policy_is_present(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")

        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    async def test_permissions_policy_is_present(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")

        assert response.headers["Permissions-Policy"] == "geolocation=(), camera=(), microphone=()"

    async def test_present_on_a_404_too(self, client: AsyncClient) -> None:
        """Headers are added by middleware wrapping the whole call chain, not inside a route --
        must show up even on a path no route matches.
        """
        response = await client.get("/api/v1/this-route-does-not-exist")

        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    async def test_present_on_a_mapped_exception_response(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """A `401` from `querymind.api.exception_handlers` is still wrapped by the same
        middleware stack -- headers must be present there too, not just on 200s.
        """
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    async def test_no_content_security_policy_on_api_responses(self, client: AsyncClient) -> None:
        """Deliberate: a JSON API renders no browser content of its own, and a CSP here would
        only risk breaking `/docs`/`/redoc`'s CDN-loaded assets for no protective benefit --
        see `querymind.api.middleware`'s own module-level docstring comment.
        """
        response = await client.get("/api/v1/health/live")

        assert "content-security-policy" not in {k.lower() for k in response.headers}


class TestAuthCacheControl:
    async def test_auth_me_is_never_cached(self, app: FastAPI, client: AsyncClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read()

        response = await client.get("/api/v1/auth/me")

        assert response.headers["Cache-Control"] == "no-store"

    async def test_login_response_is_never_cached(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_result = InvalidCredentialsError("bad credentials")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        # A failed login is exactly the kind of response that must never be cached/replayed --
        # the header must be present here, not just on a successful login.
        response = await client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "wrong"}
        )

        assert response.status_code == 401
        assert response.headers["Cache-Control"] == "no-store"

    async def test_a_non_auth_route_is_not_forced_no_store(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read()

        response = await client.get("/api/v1/health/live")

        assert response.headers.get("Cache-Control") != "no-store"


class TestHstsBehavior:
    async def test_absent_in_development(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")

        assert "strict-transport-security" not in {k.lower() for k in response.headers}

    async def test_present_in_production(self) -> None:
        async with _client(_settings(app_env="production")) as (_, prod_client):
            response = await prod_client.get("/api/v1/health/live")

            assert response.headers["Strict-Transport-Security"] == (
                "max-age=31536000; includeSubDomains"
            )

    async def test_still_absent_in_staging(self) -> None:
        """`is_production` is specifically `app_env == "production"` -- `staging` (a real,
        distinct `Environment` value) must not accidentally trigger HSTS too.
        """
        async with _client(_settings(app_env="staging")) as (_, staging_client):
            response = await staging_client.get("/api/v1/health/live")

            assert "strict-transport-security" not in {k.lower() for k in response.headers}


class TestDocsAndRedocRemainFunctional:
    """`SecurityHeadersMiddleware` never adds a CSP (see `TestBaselineHeaders
    .test_no_content_security_policy_on_api_responses`) specifically so it can never interfere
    with Swagger UI's/`ReDoc`'s CDN-loaded JS/CSS -- these tests confirm both pages still load.
    """

    async def test_docs_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/docs")

        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    async def test_redoc_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/redoc")

        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    async def test_openapi_schema_is_still_served(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        assert response.json()["info"]["title"]

    async def test_docs_still_has_baseline_headers_but_no_csp(self, client: AsyncClient) -> None:
        response = await client.get("/docs")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "content-security-policy" not in {k.lower() for k in response.headers}
