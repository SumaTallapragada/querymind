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
  `test_integration.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
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
    async with LifespanManager(app):
        asgi_transport = ASGITransport(app=app)
        async with AsyncClient(transport=asgi_transport, base_url="http://test") as ac:
            yield ac
