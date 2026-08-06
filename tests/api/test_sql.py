"""Unit tests for `POST /api/v1/query/sql`. `QueryMindEngineDep` is mocked -- verifies the
route calls `QueryMindEngine.ask_for_sql` (never `.ask`, since this endpoint must never
execute SQL) and that a wrapped stage failure maps to the right HTTP status.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_query_mind_engine
from querymind.nlu import EmptyQuestionError
from querymind.orchestrator.exceptions import PipelineExecutionError
from querymind.orchestrator.models import GeneratedSqlResult, PipelineStage
from tests.orchestrator.conftest import (
    make_generated_sql,
    make_generated_sql_result,
    make_validation_result,
)

_QUESTION = "Who are our top 5 customers by revenue?"


def _make_outcome() -> GeneratedSqlResult:
    generated_sql = make_generated_sql("SELECT customer_id FROM customers LIMIT 5;")
    validation_result = make_validation_result(generated_sql)
    return make_generated_sql_result(generated_sql, validation_result)


class _FakeEngine:
    def __init__(self, outcome: GeneratedSqlResult | Exception) -> None:
        self._outcome = outcome

    async def ask_for_sql(self, question: str) -> GeneratedSqlResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def ask(self, question: str) -> None:  # pragma: no cover
        raise AssertionError(
            "`/query/sql` must never call `QueryMindEngine.ask` -- it would execute SQL."
        )


async def test_returns_the_generated_sql_result(app: FastAPI, client: AsyncClient) -> None:
    outcome = _make_outcome()
    app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine(outcome)

    response = await client.post("/api/v1/query/sql", json={"question": _QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["original_question"] == outcome.original_question
    assert body["repair_result"] is None


async def test_a_stage_failure_maps_to_the_underlying_causes_status(
    app: FastAPI, client: AsyncClient
) -> None:
    cause = EmptyQuestionError("Question is empty.")
    wrapped = PipelineExecutionError(
        "nlu failed",
        stage=PipelineStage.NLU,
        stage_timings=(),
        repair_attempted=False,
        repair_performed=False,
        generated_sql=None,
        validation_result=None,
        repair_result=None,
        execution_result=None,
    )
    wrapped.__cause__ = cause
    app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine(wrapped)

    response = await client.post("/api/v1/query/sql", json={"question": _QUESTION})

    assert response.status_code == 400
    assert response.json()["error_type"] == "EmptyQuestionError"


async def test_an_empty_question_is_rejected_before_reaching_the_engine(
    app: FastAPI, client: AsyncClient
) -> None:
    response = await client.post("/api/v1/query/sql", json={"question": ""})

    assert response.status_code == 422
