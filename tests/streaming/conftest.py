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
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.core.config import Settings
from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
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
