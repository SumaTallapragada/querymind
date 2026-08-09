"""End-to-end tests against the real, fully wired FastAPI app -- streaming layer.

Every engine behind both `POST /query/stream` and `/ws/query` is real --
the real `ApplicationContainer`, `PipelineRunner`, and every domain
engine it wires -- against the real, already-running, seeded local
Postgres instance, with only the LLM's network replaced by
`httpx.MockTransport`. Mirrors `tests/api/test_integration.py`'s own
precedent (and reuses its exact `_VALID_SQL`/`_BROKEN_SQL`, already
proven to validate/fail against the real schema) one transport layer up:
these tests exist to prove the *streaming* of a real run works, not to
re-prove the pipeline itself, which `tests/orchestrator/test_integration.py`
and `tests/api/test_integration.py` already cover.

`TestSseIntegration` goes through `integration_client`, which already authenticates as `ADMIN`
(Phase 22B; see `tests/api/conftest.py`). `TestWebSocketIntegration` can't reuse that helper --
`/ws/query` bypasses `Depends(get_current_user)` entirely (see
`querymind.streaming.websocket`'s docstring) -- so it registers and logs in a real user over
real HTTP first, the same way `tests/api/test_auth_integration.py` does, and passes the real
access token to `websocket_connect`. `_cleanup_auth_tables` below mirrors that file's
`_clean_auth_tables` fixture, but runs on `client.portal` (`TestClient`'s own background event
loop, reusing the already-open `app.state.session_factory`/`container.engine`) while the
`TestClient` is still open, rather than a second `asyncio.run`/`create_engine` after it closes
-- opening a second, independent connection pool just for cleanup left an unclosed socket and
event loop for the garbage collector to find at a nondeterministic point in a *later* test,
which `filterwarnings = ["error"]` (`pyproject.toml`) turns into a spurious failure there.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketDisconnect

from querymind.api.app import create_app
from querymind.auth.models import RefreshToken, User, UserRole
from querymind.core.config import Settings
from querymind.llm.client import HttpxTransport
from tests.api.conftest import integration_client, sql_handler

_QUESTION = "Who are our top 10 customers by revenue?"


async def _cleanup_auth_tables(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


async def _downgrade_to_viewer(
    session_factory: async_sessionmaker[AsyncSession], username: str
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(User).where(User.username == username).values(role=UserRole.VIEWER)
        )
        await session.commit()


_VALID_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
)

_BROKEN_SQL = (
    "SELECT c.customer_id, w.warehouse_id "
    "FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
)


class TestSseIntegration:
    async def test_streams_a_real_question_end_to_end(self, real_settings: Settings) -> None:
        async with (
            integration_client(real_settings, sql_handler([_VALID_SQL])) as client,
            client.stream("POST", "/api/v1/query/stream", json={"question": _QUESTION}) as response,
        ):
            assert response.status_code == 200
            event_types = []
            final_payload = None
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event_types.append(line.removeprefix("event: "))
                if line.startswith("data: ") and "pipeline_completed" in line:
                    final_payload = json.loads(line.removeprefix("data: "))["payload"]

        assert event_types[0] == "pipeline_started"
        assert event_types[-1] == "pipeline_completed"
        assert "stage_completed" in event_types
        assert final_payload is not None
        assert final_payload["status"] == "success"
        assert final_payload["business_answer"] is not None

    async def test_streams_a_repaired_question_end_to_end(self, real_settings: Settings) -> None:
        async with (
            integration_client(real_settings, sql_handler([_BROKEN_SQL, _VALID_SQL])) as client,
            client.stream("POST", "/api/v1/query/stream", json={"question": _QUESTION}) as response,
        ):
            event_types = [
                line.removeprefix("event: ")
                async for line in response.aiter_lines()
                if line.startswith("event: ")
            ]

        assert "stage_failed" not in event_types  # repair succeeding is not a stage failure
        assert event_types.count("stage_started") == event_types.count("stage_completed")
        assert event_types[-1] == "pipeline_completed"

    async def test_disconnecting_early_leaves_the_server_usable_for_the_next_request(
        self, real_settings: Settings
    ) -> None:
        async with integration_client(real_settings, sql_handler([_VALID_SQL])) as client:
            async with client.stream(
                "POST", "/api/v1/query/stream", json={"question": _QUESTION}
            ) as response:
                async for _line in response.aiter_lines():
                    break  # stop reading after the very first line -- an early disconnect

            # The server (and its one shared ApplicationContainer/EventBus) must still be
            # healthy for a completely unrelated, subsequent request.
            health_response = await client.get("/api/v1/health/live")
            assert health_response.status_code == 200


class TestWebSocketIntegration:
    def test_streams_a_real_question_end_to_end(self, real_settings: Settings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return sql_handler([_VALID_SQL])(request)

        transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
        app = create_app(settings=real_settings, llm_transport=transport)

        with TestClient(app) as client:
            try:
                # A real registered user (default role `ANALYST`, per the Phase 22B
                # migration's `server_default`) -- `/ws/query` checks a real token against
                # the real database, unlike `tests/streaming/test_websocket.py`'s unit tests.
                username = f"ws_integration_{uuid.uuid4().hex[:8]}"
                register = client.post(
                    "/api/v1/auth/register",
                    json={
                        "username": username,
                        "email": f"{username}@example.com",
                        "password": "password123",
                    },
                )
                assert register.status_code == 201, register.text
                login = client.post(
                    "/api/v1/auth/login", json={"username": username, "password": "password123"}
                )
                assert login.status_code == 200, login.text
                access_token = login.json()["access_token"]

                with client.websocket_connect(
                    "/ws/query", headers={"Authorization": f"Bearer {access_token}"}
                ) as ws:
                    ws.send_json({"question": _QUESTION})
                    message = ws.receive_json()
                    event_types = [message["event_type"]]
                    while message["event_type"] != "pipeline_completed":
                        message = ws.receive_json()
                        event_types.append(message["event_type"])
            finally:
                client.portal.call(_cleanup_auth_tables, app.state.session_factory)

        assert event_types[0] == "pipeline_started"
        assert event_types[-1] == "pipeline_completed"
        assert message["payload"]["status"] == "success"
        assert message["payload"]["business_answer"] is not None

    def test_rejects_a_connection_with_no_token(self, real_settings: Settings) -> None:
        app = create_app(settings=real_settings)

        with (
            TestClient(app) as client,
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/query") as ws,
        ):
            ws.receive_json()

        assert exc_info.value.code == 1008

    def test_rejects_a_connection_for_a_role_below_analyst(self, real_settings: Settings) -> None:
        app = create_app(settings=real_settings)

        with TestClient(app) as client:
            try:
                # A real registered user, downgraded to `VIEWER` -- there is no HTTP endpoint
                # for this (see `test_auth_integration.py::_promote_to_admin`'s own docstring
                # for why); the direct database write is the only way to produce one.
                username = f"ws_forbidden_{uuid.uuid4().hex[:8]}"
                register = client.post(
                    "/api/v1/auth/register",
                    json={
                        "username": username,
                        "email": f"{username}@example.com",
                        "password": "password123",
                    },
                )
                assert register.status_code == 201, register.text
                login = client.post(
                    "/api/v1/auth/login", json={"username": username, "password": "password123"}
                )
                assert login.status_code == 200, login.text
                access_token = login.json()["access_token"]

                client.portal.call(_downgrade_to_viewer, app.state.session_factory, username)

                with (
                    pytest.raises(WebSocketDisconnect) as exc_info,
                    client.websocket_connect(
                        "/ws/query", headers={"Authorization": f"Bearer {access_token}"}
                    ) as ws,
                ):
                    ws.receive_json()

                assert exc_info.value.code == 1008
            finally:
                client.portal.call(_cleanup_auth_tables, app.state.session_factory)
