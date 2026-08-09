"""Unit tests for `POST /api/v1/query/format`. `ResultFormatterEngineDep` is mocked --
verifies the route accepts a bare `SQLExecutionResult` as the whole request body (no wrapper
DTO), passes it through to `ResultFormatterEngine.format` unchanged, and maps a
`FormattingError` (raised for a non-`SUCCESS` execution result) to `422`.

Requires at least `ANALYST` (Phase 22B) -- `_authenticated_as_analyst` below overrides
`get_current_user` for every test in this file; see `test_diagnostics.py`'s identical fixture
for why.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user, get_result_formatter_engine
from querymind.auth.models import UserRole
from querymind.result_formatter import FormattingError
from querymind.result_formatter.models import BusinessAnswer
from querymind.sql_execution.models import SQLExecutionResult
from tests.api.conftest import make_user_read
from tests.orchestrator.conftest import (
    make_business_answer,
    make_execution_result,
    make_generated_sql,
)

_SQL = "SELECT customer_id FROM customers LIMIT 5;"


@pytest.fixture(autouse=True)
def _authenticated_as_analyst(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)


class _FakeFormatterEngine:
    def __init__(self, outcome: BusinessAnswer | Exception) -> None:
        self._outcome = outcome
        self.received: SQLExecutionResult | None = None

    def format(self, execution_result: SQLExecutionResult) -> BusinessAnswer:
        self.received = execution_result
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


async def test_formats_a_successful_execution_result(app: FastAPI, client: AsyncClient) -> None:
    execution_result = make_execution_result(make_generated_sql(_SQL))
    answer = make_business_answer(execution_result)
    fake = _FakeFormatterEngine(answer)
    app.dependency_overrides[get_result_formatter_engine] = lambda: fake

    response = await client.post(
        "/api/v1/query/format", json=execution_result.model_dump(mode="json")
    )

    assert response.status_code == 200
    assert fake.received is not None
    assert fake.received.executed_sql == _SQL


async def test_a_formatting_error_maps_to_422(app: FastAPI, client: AsyncClient) -> None:
    execution_result = make_execution_result(make_generated_sql(_SQL))
    fake = _FakeFormatterEngine(FormattingError("Cannot format a non-successful result."))
    app.dependency_overrides[get_result_formatter_engine] = lambda: fake

    response = await client.post(
        "/api/v1/query/format", json=execution_result.model_dump(mode="json")
    )

    assert response.status_code == 422
    assert response.json()["error_type"] == "FormattingError"
