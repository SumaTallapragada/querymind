"""Unit tests for `POST /api/v1/query/validate`. `SQLValidationEngineDep` is mocked -- verifies
the route wraps externally supplied SQL in an honest, clearly-synthetic `GeneratedSQL`
placeholder (never invents or alters the SQL text itself) and returns whatever
`SQLValidationEngine.validate` reports, unchanged.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_sql_validation_engine
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.models import SQLValidationResult
from tests.orchestrator.conftest import make_generated_sql, make_issue, make_validation_result

_SQL = "SELECT customer_id FROM customers LIMIT 5;"


class _FakeValidationEngine:
    def __init__(self, result_for: SQLValidationResult) -> None:
        self._result_for = result_for
        self.received: GeneratedSQL | None = None

    def validate(self, generated_sql: GeneratedSQL) -> SQLValidationResult:
        self.received = generated_sql
        return self._result_for


async def test_wraps_the_sql_and_returns_the_validation_result(
    app: FastAPI, client: AsyncClient
) -> None:
    placeholder = make_generated_sql(_SQL)
    result = make_validation_result(placeholder)
    fake = _FakeValidationEngine(result)
    app.dependency_overrides[get_sql_validation_engine] = lambda: fake

    response = await client.post("/api/v1/query/validate", json={"sql": _SQL})

    assert response.status_code == 200
    assert response.json()["is_valid"] is True
    assert fake.received is not None
    assert fake.received.sql == _SQL
    assert fake.received.dialect is SQLDialect.POSTGRESQL


async def test_never_invents_llm_provenance_for_externally_supplied_sql(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeValidationEngine(make_validation_result(make_generated_sql(_SQL)))
    app.dependency_overrides[get_sql_validation_engine] = lambda: fake

    await client.post("/api/v1/query/validate", json={"sql": _SQL})

    assert fake.received is not None
    assert fake.received.llm_metrics.model == "external"
    assert fake.received.llm_metrics.token_usage.prompt_tokens == 0


async def test_a_reported_invalidity_still_returns_200(app: FastAPI, client: AsyncClient) -> None:
    placeholder = make_generated_sql(_SQL)
    invalid_result = make_validation_result(placeholder, errors=(make_issue("unknown_table"),))
    fake = _FakeValidationEngine(invalid_result)
    app.dependency_overrides[get_sql_validation_engine] = lambda: fake

    response = await client.post("/api/v1/query/validate", json={"sql": _SQL})

    assert response.status_code == 200
    assert response.json()["is_valid"] is False


async def test_empty_sql_is_rejected_before_reaching_the_engine(
    app: FastAPI, client: AsyncClient
) -> None:
    response = await client.post("/api/v1/query/validate", json={"sql": ""})

    assert response.status_code == 422
