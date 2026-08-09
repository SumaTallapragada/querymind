"""Unit tests for `/ws/query`. `QueryMindEngineDep` is mocked -- these tests verify the route's
own, and only, responsibilities: parsing the inbound `{"question": ...}` message, streaming one
WebSocket text frame per `PipelineEvent`, and closing cleanly (`1008` for an invalid request,
otherwise a normal close after the terminal event).

Plain, synchronous test functions throughout (not `async def`) -- `starlette.testclient.TestClient`
bridges to the ASGI app via its own thread-based portal and is not meant to be awaited from
inside an already-running event loop, unlike every other test file in this project.

Requires at least `ANALYST` (Phase 22B) -- every `client.websocket_connect(...)` call below
passes a bearer token, and every `app` is passed through `authorize_websocket_app` first
(`get_current_user` can't be overridden for `/ws/query`; see that helper's docstring, in this
package's `conftest.py`, for why). The token's value is never checked by the fake service
`authorize_websocket_app` installs -- these tests exist to prove pipeline streaming, not
authorization itself (covered by the Phase 22B authorization suite, which does check real
tokens against `/ws/query` end to end).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from querymind.api.app import create_app
from querymind.api.dependencies import get_query_mind_engine
from querymind.core.config import Settings
from querymind.orchestrator.models import PipelineStatus, QueryMindResponse

from .conftest import FakeQueryMindEngine, authorize_websocket_app, make_success_response

_QUESTION = "Who are our top 5 customers by revenue?"
_AUTH_HEADERS = {"Authorization": "Bearer test-token"}


def test_streams_one_frame_per_pipeline_event(settings: Settings) -> None:
    app = create_app(settings=settings)
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"question": _QUESTION})
        event_types = []
        while True:
            message = ws.receive_json()
            event_types.append(message["event_type"])
            if message["event_type"] in ("pipeline_completed", "pipeline_failed"):
                break

    assert event_types == [
        "pipeline_started",
        "stage_started",
        "stage_completed",
        "pipeline_completed",
    ]


def test_the_final_message_carries_the_response_status(settings: Settings) -> None:
    app = create_app(settings=settings)
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"question": _QUESTION})
        message = ws.receive_json()
        while message["event_type"] != "pipeline_completed":
            message = ws.receive_json()

    assert message["payload"]["status"] == "success"


def test_a_soft_pipeline_failure_still_streams_a_pipeline_completed_message(
    settings: Settings,
) -> None:
    app = create_app(settings=settings)
    failed_response = QueryMindResponse(
        original_question=_QUESTION,
        statistics=make_success_response(_QUESTION).statistics,
        status=PipelineStatus.FAILED,
        error="execution rejected",
    )
    engine = FakeQueryMindEngine(failed_response)
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"question": _QUESTION})
        message = ws.receive_json()
        while message["event_type"] != "pipeline_completed":
            message = ws.receive_json()

    assert message["payload"]["status"] == "failed"
    assert message["payload"]["error"] == "execution rejected"


def test_every_message_carries_the_same_correlation_id(settings: Settings) -> None:
    app = create_app(settings=settings)
    engine = FakeQueryMindEngine(make_success_response(_QUESTION))
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"question": _QUESTION})
        messages = [ws.receive_json()]
        while messages[-1]["event_type"] != "pipeline_completed":
            messages.append(ws.receive_json())

    correlation_ids = {message["correlation_id"] for message in messages}
    assert len(correlation_ids) == 1


def test_an_invalid_message_closes_with_policy_violation(settings: Settings) -> None:
    app = create_app(settings=settings)
    engine = FakeQueryMindEngine(make_success_response())
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"not_a_question": "oops"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == 1008

    assert engine.received_questions == []


def test_an_empty_question_closes_with_policy_violation(settings: Settings) -> None:
    app = create_app(settings=settings)
    engine = FakeQueryMindEngine(make_success_response())
    app.dependency_overrides[get_query_mind_engine] = lambda: engine
    authorize_websocket_app(app)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/query", headers=_AUTH_HEADERS) as ws,
    ):
        ws.send_json({"question": ""})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == 1008
