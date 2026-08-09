"""Shared fixtures and builders for `tests/streaming`.

`app`/`client` mirror `tests/api/conftest.py`'s own fixtures of the same
name exactly (a `FastAPI` object exposing `dependency_overrides`, and a
lifespan-managed `AsyncClient` built on top of it) -- redefined here,
not inherited, since pytest only discovers a `conftest.py`'s fixtures
for the directory it's in and that directory's *subdirectories*;
`tests/streaming` is a sibling of `tests/api`, not nested inside it.

`real_settings` mirrors `tests/api/conftest.py`'s fixture of the same
name for the same reason: real `Settings()`, read from `.env` -- the
actual, already-running local Postgres instance -- used only by
`test_integration.py`.

`FakeQueryMindEngine` is this package's one recurring test double: a
`QueryMindEngine`-shaped fake whose `.ask` drives a supplied
`event_publisher` through a scripted sequence of stage callbacks before
returning or raising -- controllable enough to test `stream_pipeline_events`,
`POST /query/stream`, and `/ws/query` without a real pipeline, mirroring
`tests/orchestrator/test_engine.py`'s own `_FakeRunner` precedent one
layer up.

`authorize_websocket_app` (Phase 22B) is `/ws/query`'s equivalent of overriding
`get_current_user`: that dependency override has no effect on `/ws/query`, since
`querymind.streaming.websocket._authenticate_and_authorize` reaches
`container.authentication_service` directly rather than through `Depends()` (a WebSocket route
can't use `OAuth2PasswordBearer` -- see that module's own docstring for why). This overrides
`get_container` instead, with a copy of the real, already-built container whose
`authentication_service` is swapped for `_FakeWsAuthenticationService` -- every other engine
`/ws/query` resolves off the container (`QueryMindEngineDep`, `EventBusDep`, `LoggerDep`) is
either independently overridden by the test or comes through unchanged, since `dataclasses.replace`
only touches the one field.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from typing import cast

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.api.container import ApplicationContainer
from querymind.api.dependencies import get_container
from querymind.auth.exceptions import ForbiddenRoleError
from querymind.auth.models import UserRole
from querymind.auth.schemas import UserRead
from querymind.core.config import Settings
from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
)
from tests.api.conftest import make_user_read

_ROLE_RANK = {UserRole.VIEWER: 1, UserRole.ANALYST: 2, UserRole.ADMIN: 3}


class _FakeWsAuthenticationService:
    """Duck-typed stand-in for `container.authentication_service`, accepting any non-empty
    token as `role` -- these tests exist to prove pipeline streaming over WebSocket, not
    authentication/authorization itself (covered by `tests/auth`, `tests/api/test_dependencies.py`,
    and the Phase 22B authorization suite, the latter using a real token against a real
    database for `/ws/query` specifically).
    """

    def __init__(self, role: UserRole) -> None:
        self._role = role

    async def get_current_user(self, access_token: str) -> UserRead:
        return make_user_read(role=self._role)

    def require_role(self, user: UserRead, minimum_role: UserRole) -> None:
        if _ROLE_RANK[cast(UserRole, user.role)] < _ROLE_RANK[minimum_role]:
            raise ForbiddenRoleError(
                f"This action requires at least the {minimum_role.value!r} role; "
                f"the current user has {user.role.value!r}."
            )


def authorize_websocket_app(app: FastAPI, role: UserRole = UserRole.ANALYST) -> None:
    """Make `/ws/query` accept any token as `role` for `app`, without a real database.

    Safe to call any time before the request is issued -- the override is a lazily evaluated
    callable, so `app.state.container` only needs to exist by the time a request actually
    arrives (after the app's lifespan has started), not when this function runs.
    """
    app.dependency_overrides[get_container] = lambda: dataclasses.replace(
        cast(ApplicationContainer, app.state.container),
        authentication_service=_FakeWsAuthenticationService(role),  # type: ignore[arg-type]
    )


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


def make_success_response(question: str = "Who are our top customers?") -> QueryMindResponse:
    return QueryMindResponse(
        original_question=question,
        statistics=PipelineStatistics(
            total_latency_ms=5.0,
            stage_timings=(),
            repair_attempted=False,
            repair_performed=False,
        ),
        status=PipelineStatus.SUCCESS,
        error=None,
    )


class FakeQueryMindEngine:
    """A `QueryMindEngine`-shaped fake. `.ask` drives `event_publisher` (if given) through
    `pipeline_started` -> one `stage_started`/`stage_completed` pair per stage in `stages`
    (sleeping `delay_seconds` before each `stage_completed`, if set) -> either
    `pipeline_completed(response)` or, if `raise_error` was given, raising it directly
    (bypassing the "never raises" contract `QueryMindEngine.ask` really has -- for exercising
    `stream_pipeline_events`'s defensive fallback path only).
    """

    def __init__(
        self,
        response: QueryMindResponse | None = None,
        *,
        raise_error: BaseException | None = None,
        delay_seconds: float = 0.0,
        stages: tuple[PipelineStage, ...] = (PipelineStage.NLU,),
    ) -> None:
        self._response = response if response is not None else make_success_response()
        self._raise_error = raise_error
        self._delay_seconds = delay_seconds
        self._stages = stages
        self.received_questions: list[str] = []

    async def ask(
        self, question: str, *, event_publisher: StageEventPublisher | None = None
    ) -> QueryMindResponse:
        self.received_questions.append(question)
        if event_publisher is not None:
            await event_publisher.pipeline_started(original_question=question)
            for stage in self._stages:
                await event_publisher.stage_started(stage)
                if self._delay_seconds:
                    await asyncio.sleep(self._delay_seconds)
                await event_publisher.stage_completed(stage, duration_ms=1.0)

        if self._raise_error is not None:
            raise self._raise_error

        if event_publisher is not None:
            await event_publisher.pipeline_completed(self._response)
        return self._response
