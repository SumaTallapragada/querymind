"""Unit tests for `POST /api/v1/query/stream`. `QueryMindEngineDep` is mocked -- these tests
verify the route's own, and only, responsibilities: validating the request body, streaming
`text/event-stream` frames for whatever `stream_pipeline_events` yields, and reusing the same
correlation ID `RequestContextMiddleware` already bound to this request.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_query_mind_engine
from querymind.orchestrator.models import PipelineStatus, QueryMindResponse

from .conftest import FakeQueryMindEngine, make_success_response

_QUESTION = "Who are our top 5 customers by revenue?"


def _parse_sse_frames(raw_body: str) -> list[dict[str, Any]]:
    """Parse one or more `event:`/`data:`-shaped SSE frames into their decoded `data:` payloads."""
    frames = [block for block in raw_body.split("\n\n") if block.strip()]
    parsed: list[dict[str, Any]] = []
    for frame in frames:
        data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
        parsed.append(json.loads(data_line.removeprefix("data: ")))
    return parsed


async def test_streams_one_frame_per_pipeline_event(app: FastAPI, client: AsyncClient) -> None:
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine

    async with client.stream(
        "POST", "/api/v1/query/stream", json={"question": _QUESTION}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])

    events = _parse_sse_frames(body)
    assert [e["event_type"] for e in events] == [
        "pipeline_started",
        "stage_started",
        "stage_completed",
        "pipeline_completed",
    ]


async def test_the_final_frame_carries_the_response_status(
    app: FastAPI, client: AsyncClient
) -> None:
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine

    async with client.stream(
        "POST", "/api/v1/query/stream", json={"question": _QUESTION}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    events = _parse_sse_frames(body)
    assert events[-1]["payload"]["status"] == "success"


async def test_a_soft_pipeline_failure_still_streams_a_pipeline_completed_frame(
    app: FastAPI, client: AsyncClient
) -> None:
    failed_response = QueryMindResponse(
        original_question=_QUESTION,
        statistics=make_success_response(_QUESTION).statistics,
        status=PipelineStatus.FAILED,
        error="execution rejected",
    )
    engine = FakeQueryMindEngine(failed_response)
    app.dependency_overrides[get_query_mind_engine] = lambda: engine

    async with client.stream(
        "POST", "/api/v1/query/stream", json={"question": _QUESTION}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    events = _parse_sse_frames(body)
    assert events[-1]["event_type"] == "pipeline_completed"
    assert events[-1]["payload"]["status"] == "failed"
    assert events[-1]["payload"]["error"] == "execution rejected"


async def test_every_event_carries_the_same_correlation_id_as_the_response_header(
    app: FastAPI, client: AsyncClient
) -> None:
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine

    async with client.stream(
        "POST", "/api/v1/query/stream", json={"question": _QUESTION}
    ) as response:
        correlation_id_header = response.headers["X-Correlation-ID"]
        body = "".join([chunk async for chunk in response.aiter_text()])

    events = _parse_sse_frames(body)
    assert all(e["correlation_id"] == correlation_id_header for e in events)


async def test_an_empty_question_is_rejected_before_reaching_the_engine(
    app: FastAPI, client: AsyncClient
) -> None:
    engine = FakeQueryMindEngine(make_success_response())
    app.dependency_overrides[get_query_mind_engine] = lambda: engine

    response = await client.post("/api/v1/query/stream", json={"question": ""})

    assert response.status_code == 422
    assert engine.received_questions == []
