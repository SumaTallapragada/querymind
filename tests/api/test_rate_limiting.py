"""End-to-end tests for Phase 22D rate limiting, through real HTTP requests against a fully
wired app (`create_app`) -- `AuthenticationServiceDep`/`QueryMindEngineDep` are mocked, mirroring
`test_query.py`/`test_auth.py`'s own style, but the `RateLimiter` itself is the *real*
`InMemoryTokenBucketRateLimiter` the container builds from `Settings.rate_limit_enabled`. Each
test builds its own app from a `Settings` instance with a deliberately tiny limit for the one
scope it's testing, so a handful of real HTTP requests -- never real time -- is enough to
exhaust a bucket.

`tests/security/test_rate_limiter.py` covers the token-bucket algorithm itself in isolation;
`tests/api/test_rate_limit_dependencies.py` covers each dependency's own key-composition logic
directly; this file is what proves the whole stack -- settings, container, dependency, route,
exception handler -- actually produces a `429` with the right body and header.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.api.dependencies import (
    get_authentication_service,
    get_current_user,
    get_query_mind_engine,
)
from querymind.auth.models import UserRole
from querymind.core.config import Settings
from querymind.orchestrator.models import PipelineStatistics, PipelineStatus, QueryMindResponse
from tests.api.conftest import FakeAuthenticationService, make_token_pair, make_user_read

_QUESTION = "Who are our top 5 customers by revenue?"


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


def _success_response() -> QueryMindResponse:
    return QueryMindResponse(
        original_question=_QUESTION,
        statistics=PipelineStatistics(
            total_latency_ms=1.0, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
        status=PipelineStatus.SUCCESS,
        error=None,
    )


class _FakeEngine:
    async def ask(self, question: str) -> QueryMindResponse:
        return _success_response()


class TestGeneralCeiling:
    async def test_a_generous_limit_never_blocks_a_handful_of_requests(self) -> None:
        async with _client(_settings(rate_limit_general_per_minute=300)) as (_, client):
            for _ in range(5):
                response = await client.get("/api/v1/health/live")
                assert response.status_code == 200

    async def test_covers_a_route_with_no_more_specific_limit(self) -> None:
        async with _client(_settings(rate_limit_general_per_minute=2)) as (_, client):
            assert (await client.get("/api/v1/health/live")).status_code == 200
            assert (await client.get("/api/v1/health/live")).status_code == 200

            blocked = await client.get("/api/v1/health/live")

            assert blocked.status_code == 429
            assert blocked.json()["error_type"] == "RateLimitExceededError"
            assert "Retry-After" in blocked.headers


class TestLoginRateLimitHttp:
    async def test_blocks_after_the_configured_number_of_attempts(self) -> None:
        async with _client(_settings(rate_limit_login_per_minute=2)) as (app, client):
            fake = FakeAuthenticationService()
            fake.authenticate_result = make_user_read(username="alice")
            fake.create_token_pair_result = make_token_pair()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            for _ in range(2):
                response = await client.post(
                    "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
                )
                assert response.status_code == 200

            blocked = await client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
            )

            assert blocked.status_code == 429
            assert blocked.json()["error_type"] == "RateLimitExceededError"

    async def test_separate_usernames_do_not_interfere(self) -> None:
        """`trust_proxy_headers=True` + distinct `X-Forwarded-For` values isolates the username
        dimension from the IP dimension -- both `client.post(...)` calls otherwise share the
        same loopback test-client IP, which would exhaust the IP bucket first and make this
        test pass for the wrong reason (`tests/api/test_rate_limit_dependencies.py`'s own
        `TestLoginRateLimit.test_separate_usernames_use_separate_keys` isolates the same claim
        even more directly, with a fake limiter).
        """
        async with _client(_settings(rate_limit_login_per_minute=1, trust_proxy_headers=True)) as (
            app,
            client,
        ):
            fake = FakeAuthenticationService()
            fake.authenticate_result = make_user_read()
            fake.create_token_pair_result = make_token_pair()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            first = await client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "x"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            second = await client.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "x"},
                headers={"X-Forwarded-For": "10.0.0.2"},
            )

            assert first.status_code == 200
            assert second.status_code == 200

    async def test_the_same_username_is_blocked_even_from_different_ips(self) -> None:
        """The credential-stuffing scenario the username bucket exists for: the same attempted
        username, from two different source IPs, is still throttled by the second request even
        though each IP's own bucket is nowhere near exhausted.
        """
        async with _client(_settings(rate_limit_login_per_minute=1, trust_proxy_headers=True)) as (
            app,
            client,
        ):
            fake = FakeAuthenticationService()
            fake.authenticate_result = make_user_read()
            fake.create_token_pair_result = make_token_pair()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            first = await client.post(
                "/api/v1/auth/login",
                json={"username": "mallory", "password": "guess1"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            second = await client.post(
                "/api/v1/auth/login",
                json={"username": "mallory", "password": "guess2"},
                headers={"X-Forwarded-For": "10.0.0.2"},
            )

            assert first.status_code == 200
            assert second.status_code == 429


class TestRegisterRateLimitHttp:
    async def test_blocks_after_the_configured_number_of_attempts(self) -> None:
        async with _client(_settings(rate_limit_register_per_hour=2)) as (app, client):
            fake = FakeAuthenticationService()
            fake.register_user_result = make_user_read()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            for i in range(2):
                response = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "username": f"user{i}",
                        "email": f"user{i}@example.com",
                        "password": "password123",
                    },
                )
                assert response.status_code == 201

            blocked = await client.post(
                "/api/v1/auth/register",
                json={"username": "user2", "email": "user2@example.com", "password": "password123"},
            )

            assert blocked.status_code == 429


class TestRefreshRateLimitHttp:
    async def test_blocks_after_the_configured_number_of_attempts(self) -> None:
        async with _client(_settings(rate_limit_refresh_per_minute=2)) as (app, client):
            fake = FakeAuthenticationService()
            fake.refresh_tokens_result = make_token_pair()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            for _ in range(2):
                response = await client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": "some.refresh.token"}
                )
                assert response.status_code == 200

            blocked = await client.post(
                "/api/v1/auth/refresh", json={"refresh_token": "some.refresh.token"}
            )

            assert blocked.status_code == 429


class TestLogoutUsesOnlyTheGeneralCeiling:
    async def test_a_tight_login_limit_does_not_affect_logout(self) -> None:
        async with _client(_settings(rate_limit_login_per_minute=1)) as (app, client):
            fake = FakeAuthenticationService()
            app.dependency_overrides[get_authentication_service] = lambda: fake

            for _ in range(5):
                response = await client.post(
                    "/api/v1/auth/logout", json={"refresh_token": "some.refresh.token"}
                )
                assert response.status_code == 204


class TestQueryRateLimitHttp:
    async def test_blocks_after_the_configured_number_of_requests(self) -> None:
        async with _client(_settings(rate_limit_query_per_minute=2)) as (app, client):
            app.dependency_overrides[get_current_user] = lambda: make_user_read(
                id=1, role=UserRole.ANALYST
            )
            app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine()

            for _ in range(2):
                response = await client.post("/api/v1/query", json={"question": _QUESTION})
                assert response.status_code == 200

            blocked = await client.post("/api/v1/query", json={"question": _QUESTION})

            assert blocked.status_code == 429
            assert blocked.json()["error_type"] == "RateLimitExceededError"
            assert "Retry-After" in blocked.headers
            assert int(blocked.headers["Retry-After"]) > 0

    async def test_separate_authenticated_users_do_not_interfere(self) -> None:
        async with _client(_settings(rate_limit_query_per_minute=1)) as (app, client):
            app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine()

            app.dependency_overrides[get_current_user] = lambda: make_user_read(
                id=1, role=UserRole.ANALYST
            )
            first_user_response = await client.post("/api/v1/query", json={"question": _QUESTION})

            app.dependency_overrides[get_current_user] = lambda: make_user_read(
                id=2, role=UserRole.ANALYST
            )
            second_user_response = await client.post("/api/v1/query", json={"question": _QUESTION})

            assert first_user_response.status_code == 200
            assert second_user_response.status_code == 200


class TestApiKeyAuthenticatedQueryUsesOwningUserIdentity:
    async def test_an_api_key_shares_its_owners_bucket_with_their_jwt(self) -> None:
        """The same user, id 99, hits the limit via JWT first -- then an API key that resolves
        to that *same* user is blocked too, proving both credential types share one bucket
        keyed on the owning user, not a second identity system.
        """
        async with _client(_settings(rate_limit_query_per_minute=1)) as (app, client):
            owner = make_user_read(id=99, role=UserRole.ANALYST)
            fake = FakeAuthenticationService()
            fake.get_current_user_result = owner
            fake.authenticate_api_key_result = owner
            app.dependency_overrides[get_authentication_service] = lambda: fake
            app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine()

            via_jwt = await client.post(
                "/api/v1/query",
                json={"question": _QUESTION},
                headers={"Authorization": "Bearer a.valid.token"},
            )
            via_api_key = await client.post(
                "/api/v1/query",
                json={"question": _QUESTION},
                headers={"X-API-Key": "qm_some-key"},
            )

            assert via_jwt.status_code == 200
            assert via_api_key.status_code == 429

    async def test_a_different_users_api_key_is_unaffected(self) -> None:
        async with _client(_settings(rate_limit_query_per_minute=1)) as (app, client):
            fake = FakeAuthenticationService()
            fake.get_current_user_result = make_user_read(id=1, role=UserRole.ANALYST)
            fake.authenticate_api_key_result = make_user_read(id=2, role=UserRole.ANALYST)
            app.dependency_overrides[get_authentication_service] = lambda: fake
            app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine()

            via_jwt = await client.post(
                "/api/v1/query",
                json={"question": _QUESTION},
                headers={"Authorization": "Bearer a.valid.token"},
            )
            via_other_users_api_key = await client.post(
                "/api/v1/query",
                json={"question": _QUESTION},
                headers={"X-API-Key": "qm_some-other-key"},
            )

            assert via_jwt.status_code == 200
            assert via_other_users_api_key.status_code == 200


class TestDisabledRateLimiting:
    async def test_bypasses_cleanly_even_with_a_tiny_configured_limit(self) -> None:
        async with _client(
            _settings(rate_limit_enabled=False, rate_limit_general_per_minute=1)
        ) as (_, client):
            for _ in range(10):
                response = await client.get("/api/v1/health/live")
                assert response.status_code == 200

    async def test_bypasses_the_query_limit_too(self) -> None:
        async with _client(_settings(rate_limit_enabled=False, rate_limit_query_per_minute=1)) as (
            app,
            client,
        ):
            app.dependency_overrides[get_current_user] = lambda: make_user_read(
                role=UserRole.ANALYST
            )
            app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine()

            for _ in range(5):
                response = await client.post("/api/v1/query", json={"question": _QUESTION})
                assert response.status_code == 200


class TestNoInformationLeakageIn429Responses:
    async def test_the_body_has_only_the_standard_error_shape(self) -> None:
        async with _client(_settings(rate_limit_general_per_minute=1)) as (_, client):
            await client.get("/api/v1/health/live")
            blocked = await client.get("/api/v1/health/live")

            assert blocked.status_code == 429
            body = blocked.json()
            assert set(body.keys()) == {"detail", "error_type"}
            assert body["error_type"] == "RateLimitExceededError"

    async def test_the_detail_message_is_generic(self) -> None:
        async with _client(_settings(rate_limit_general_per_minute=1)) as (_, client):
            await client.get("/api/v1/health/live")
            blocked = await client.get("/api/v1/health/live")

            detail = blocked.json()["detail"].lower()
            for forbidden in ("bucket", "token", "capacity", "general:ip", "127.0.0.1"):
                assert forbidden not in detail

    async def test_retry_after_is_a_positive_integer_string(self) -> None:
        async with _client(_settings(rate_limit_general_per_minute=1)) as (_, client):
            await client.get("/api/v1/health/live")
            blocked = await client.get("/api/v1/health/live")

            retry_after = blocked.headers["Retry-After"]
            assert retry_after.isdigit()
            assert int(retry_after) > 0
