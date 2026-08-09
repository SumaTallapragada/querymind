"""Shared fixtures and builders for `tests/api`.

`settings`/`client` are inherited unchanged from `tests/conftest.py`
(hermetic, deliberately pointed at an unreachable database) -- used by
every unit test in this package, which mocks the one engine dependency
its route actually calls (per this phase's "unit tests should mock
QueryMindEngine" rule) and therefore never needs a real database or LLM.

This module adds:

- `app`: the `FastAPI` object itself (not just an `AsyncClient`), so a
  unit test can install `app.dependency_overrides[...]` before issuing a
  request. `client` is redefined here, on top of `app`, purely to expose
  it and to clear overrides between tests -- its own behavior (a
  lifespan-managed `AsyncClient` over an in-process ASGI transport) is
  unchanged from `tests/conftest.py`'s own `client`, so
  `tests/api/test_health.py` (which predates this phase and only uses
  `client`) is unaffected.
- `real_settings`: real `Settings()`, read from `.env` -- the actual,
  already-running local Postgres instance. Mirrors
  `tests/orchestrator/conftest.py`/`tests/sql_execution/conftest.py`'s
  own precedent; used only by `test_execution.py` and
  `test_integration.py`, the two files that need a real database.
- `integration_client`: builds a client backed by the *complete real
  pipeline* -- every engine real, only the LLM's outbound HTTP transport
  replaced by `httpx.MockTransport` (per Phase 10B/11A/11B/12/
  `tests/orchestrator/conftest.py`'s precedent) -- for
  `test_integration.py`. Also overrides `get_current_user` to an `ADMIN` `UserRead` (Phase
  22B): every route this helper exercises now requires at least `ANALYST`, and this file's own
  tests exist to prove the pipeline, not authorization (covered separately in `tests/auth`/
  `tests/api/test_dependencies.py`/the new Phase 22B test suite) -- mirrors the per-file
  `autouse` fixture every other now-protected test file in this package adds for the same
  reason.
- `FakeAuthenticationService`/`make_user_read`/`make_token_pair` (Phase 22A Part 2): the
  `AuthenticationServiceDep` stand-in `test_auth.py` and `test_dependencies.py` both override,
  mirroring `test_query.py`'s `_FakeEngine`/`get_query_mind_engine` pattern exactly, shared here
  rather than duplicated across the two files that need it. `make_user_read` defaults to
  `role=ADMIN` (Phase 22B) so a caller that doesn't care about role -- most of `test_auth.py`
  -- never has to think about it; a role-sensitive test overrides it explicitly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.api.dependencies import get_current_user
from querymind.auth.models import UserRole
from querymind.auth.repository import AuthenticationRepository
from querymind.auth.schemas import TokenPair, UserRead
from querymind.auth.service import AuthenticationService
from querymind.core.config import Settings
from querymind.llm.client import HttpxTransport


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings=settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def real_settings() -> Settings:
    return Settings()


def claude_success_body(text: str) -> dict[str, object]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 200, "output_tokens": 50},
    }


def sql_handler(sql_texts: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    """A mock transport handler that replies with `sql_texts` in order, one per call --
    mirrors `tests/orchestrator/conftest.py`'s `sequential_sql_handler`."""
    remaining = list(sql_texts)

    def handler(request: httpx.Request) -> httpx.Response:
        text = remaining.pop(0)
        return httpx.Response(200, json=claude_success_body(f"```sql\n{text}\n```"))

    return handler


@asynccontextmanager
async def integration_client(
    settings: Settings, handler: Callable[[httpx.Request], httpx.Response]
) -> AsyncIterator[AsyncClient]:
    """A client wired to a fully real `ApplicationContainer` -- only the LLM's network
    transport is replaced, via `create_app`'s `llm_transport` seam."""
    llm_transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    app = create_app(settings=settings, llm_transport=llm_transport)
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ADMIN)
    async with LifespanManager(app):
        asgi_transport = ASGITransport(app=app)
        async with AsyncClient(transport=asgi_transport, base_url="http://test") as ac:
            yield ac


# -- Phase 22A Part 2: AuthenticationService test double ---------------------------------------


def _resolve(value: object) -> object:
    if isinstance(value, Exception):
        raise value
    return value


#: A real `AuthenticationService`, built with a repository that's never called -- `has_role`/
#: `is_admin`/`require_role`/`require_any_role` are pure functions of an already-resolved
#: `UserRead` (no repository, no JWT), so `FakeAuthenticationService` delegates its own copies
#: of those four methods to this instead of reimplementing the rank table a second time (Phase
#: 22B's "no duplicated authorization logic" -- test doubles included).
_real_service_for_authorization = AuthenticationService(
    cast(AuthenticationRepository, None), jwt_secret_key="unused-authorization-only"
)


class FakeAuthenticationService:
    """A hand-written stand-in for `AuthenticationService`, mirroring `_FakeEngine` in
    `test_query.py`. Each method's outcome is configurable via a public `..._result`/
    `..._exception` attribute (defaulting to `NotImplementedError`, so an unconfigured call
    fails loudly rather than silently returning `None`); every call is recorded for assertions.

    `has_role`/`is_admin`/`require_role`/`require_any_role` (Phase 22B) are the exception --
    not configurable, since they're pure and deterministic; see
    `_real_service_for_authorization` above for why they delegate rather than reimplement.
    """

    def __init__(self) -> None:
        self.register_user_result: object = NotImplementedError("register_user not configured")
        self.authenticate_result: object = NotImplementedError("authenticate not configured")
        self.create_token_pair_result: object = NotImplementedError(
            "create_token_pair not configured"
        )
        self.refresh_tokens_result: object = NotImplementedError("refresh_tokens not configured")
        self.logout_exception: Exception | None = None
        self.get_current_user_result: object = NotImplementedError(
            "get_current_user not configured"
        )

        self.register_calls: list[dict[str, str]] = []
        self.authenticate_calls: list[tuple[str, str]] = []
        self.create_token_pair_calls: list[int] = []
        self.refresh_tokens_calls: list[str] = []
        self.logout_calls: list[str] = []
        self.get_current_user_calls: list[str] = []

    async def register_user(self, *, username: str, email: str, password: str) -> UserRead:
        self.register_calls.append({"username": username, "email": email, "password": password})
        return _resolve(self.register_user_result)  # type: ignore[return-value]

    async def authenticate(self, username: str, password: str) -> UserRead:
        self.authenticate_calls.append((username, password))
        return _resolve(self.authenticate_result)  # type: ignore[return-value]

    async def create_token_pair(self, user_id: int) -> TokenPair:
        self.create_token_pair_calls.append(user_id)
        return _resolve(self.create_token_pair_result)  # type: ignore[return-value]

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        self.refresh_tokens_calls.append(refresh_token)
        return _resolve(self.refresh_tokens_result)  # type: ignore[return-value]

    async def logout(self, refresh_token: str) -> None:
        self.logout_calls.append(refresh_token)
        if self.logout_exception is not None:
            raise self.logout_exception

    async def get_current_user(self, access_token: str) -> UserRead:
        self.get_current_user_calls.append(access_token)
        return _resolve(self.get_current_user_result)  # type: ignore[return-value]

    def has_role(self, user: UserRead, role: UserRole) -> bool:
        return _real_service_for_authorization.has_role(user, role)

    def is_admin(self, user: UserRead) -> bool:
        return _real_service_for_authorization.is_admin(user)

    def require_role(self, user: UserRead, minimum_role: UserRole) -> None:
        _real_service_for_authorization.require_role(user, minimum_role)

    def require_any_role(self, user: UserRead, *roles: UserRole) -> None:
        _real_service_for_authorization.require_any_role(user, *roles)


def make_user_read(**overrides: object) -> UserRead:
    defaults: dict[str, object] = {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
        "is_active": True,
        "is_superuser": False,
        "role": UserRole.ADMIN,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return UserRead(**defaults)  # type: ignore[arg-type]


def make_token_pair() -> TokenPair:
    return TokenPair(access_token="access.token.value", refresh_token="refresh.token.value")
