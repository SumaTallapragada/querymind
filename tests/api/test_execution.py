"""Tests for `POST /api/v1/query/execute`.

Unit tests mock `SQLExecutionEngineDep` -- verifying the route extracts
`validation_result.generated_sql` and passes both it and the validation
result through to `SQLExecutionEngine.execute` unchanged, and that a
rejected/failed execution still returns `200` (the route never raises for
those; `status` on the body is how a caller distinguishes them).

`test_executes_read_only_sql_against_the_real_database` is the one real
test here: it uses `real_settings` (the actual, already-running local
Postgres instance, per `tests/sql_execution/conftest.py`'s own
precedent) and no mocking at all, since `SQLExecutionEngine.execute`
takes no LLM in its path.

Requires at least `ANALYST` (Phase 22B) -- `_authenticated_as_analyst` below overrides
`get_current_user` for the two unit tests (built on the shared `app`/`client` fixtures); see
`test_diagnostics.py`'s identical fixture for why. The real-database test builds its own `app`
directly (no shared fixture to attach an `autouse` fixture to), so it overrides inline instead.
"""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.api.dependencies import get_current_user, get_sql_execution_engine
from querymind.auth.models import UserRole
from querymind.core.config import Settings
from querymind.sql_execution.models import ExecutionStatus, SQLExecutionResult
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.models import SQLValidationResult
from tests.api.conftest import make_user_read
from tests.orchestrator.conftest import (
    make_execution_result,
    make_generated_sql,
    make_validation_result,
)

_SQL = "SELECT customer_id FROM customers LIMIT 5;"


@pytest.fixture(autouse=True)
def _authenticated_as_analyst(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)


class _FakeExecutionEngine:
    def __init__(self, result: SQLExecutionResult) -> None:
        self._result = result
        self.calls: list[tuple[GeneratedSQL, SQLValidationResult]] = []

    async def execute(
        self, generated_sql: GeneratedSQL, validation_result: SQLValidationResult
    ) -> SQLExecutionResult:
        self.calls.append((generated_sql, validation_result))
        return self._result


async def test_extracts_generated_sql_from_the_validation_result(
    app: FastAPI, client: AsyncClient
) -> None:
    generated_sql = make_generated_sql(_SQL)
    validation_result = make_validation_result(generated_sql)
    fake = _FakeExecutionEngine(make_execution_result(generated_sql))
    app.dependency_overrides[get_sql_execution_engine] = lambda: fake

    response = await client.post(
        "/api/v1/query/execute",
        json={"validation_result": validation_result.model_dump(mode="json")},
    )

    assert response.status_code == 200
    assert len(fake.calls) == 1
    called_sql, called_validation_result = fake.calls[0]
    assert called_sql.sql == _SQL
    assert called_validation_result.generated_sql.sql == _SQL


async def test_a_rejected_execution_still_returns_200(app: FastAPI, client: AsyncClient) -> None:
    generated_sql = make_generated_sql("DELETE FROM customers;")
    validation_result = make_validation_result(generated_sql)
    rejected = make_execution_result(generated_sql, status=ExecutionStatus.REJECTED)
    app.dependency_overrides[get_sql_execution_engine] = lambda: _FakeExecutionEngine(rejected)

    response = await client.post(
        "/api/v1/query/execute",
        json={"validation_result": validation_result.model_dump(mode="json")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


async def test_executes_read_only_sql_against_the_real_database(real_settings: Settings) -> None:
    generated_sql = make_generated_sql(_SQL)
    validation_result = make_validation_result(generated_sql)
    app = create_app(settings=real_settings)
    # Not the shared `app` fixture the module-level `_authenticated_as_analyst` overrides --
    # this test builds its own, so it overrides directly on it instead.
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/query/execute",
                json={"validation_result": validation_result.model_dump(mode="json")},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["query_result"] is not None
