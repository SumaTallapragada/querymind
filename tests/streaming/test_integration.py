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
"""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from querymind.api.app import create_app
from querymind.core.config import Settings
from querymind.llm.client import HttpxTransport
from tests.api.conftest import integration_client, sql_handler

_QUESTION = "Who are our top 10 customers by revenue?"

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

        with TestClient(app) as client, client.websocket_connect("/ws/query") as ws:
            ws.send_json({"question": _QUESTION})
            message = ws.receive_json()
            event_types = [message["event_type"]]
            while message["event_type"] != "pipeline_completed":
                message = ws.receive_json()
                event_types.append(message["event_type"])

        assert event_types[0] == "pipeline_started"
        assert event_types[-1] == "pipeline_completed"
        assert message["payload"]["status"] == "success"
        assert message["payload"]["business_answer"] is not None
