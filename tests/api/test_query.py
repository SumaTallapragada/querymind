"""Unit tests for `POST /api/v1/query`. `QueryMindEngineDep` is mocked -- these tests verify
the route's own, and only, responsibilities: validating the request body, calling
`QueryMindEngine.ask`, recording metrics from the response, and returning it unchanged.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_metrics_collector, get_query_mind_engine
from querymind.observability.metrics import InMemoryMetricsCollector
from querymind.orchestrator.models import PipelineStatistics, PipelineStatus, QueryMindResponse
from tests.orchestrator.conftest import (
    make_business_answer,
    make_execution_result,
    make_generated_sql,
    make_validation_result,
)

_QUESTION = "Who are our top 5 customers by revenue?"


def _make_success_response() -> QueryMindResponse:
    generated_sql = make_generated_sql("SELECT customer_id FROM customers LIMIT 5;")
    validation_result = make_validation_result(generated_sql)
    execution_result = make_execution_result(generated_sql)
    return QueryMindResponse(
        original_question=_QUESTION,
        business_answer=make_business_answer(execution_result),
        generated_sql=generated_sql,
        validation_result=validation_result,
        repair_result=None,
        execution_result=execution_result,
        statistics=PipelineStatistics(
            total_latency_ms=42.0, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
        status=PipelineStatus.SUCCESS,
        error=None,
    )


class _FakeEngine:
    def __init__(self, response: QueryMindResponse) -> None:
        self._response = response
        self.questions_asked: list[str] = []

    async def ask(self, question: str) -> QueryMindResponse:
        self.questions_asked.append(question)
        return self._response


async def test_returns_the_engines_response_verbatim(app: FastAPI, client: AsyncClient) -> None:
    response = _make_success_response()
    fake = _FakeEngine(response)
    app.dependency_overrides[get_query_mind_engine] = lambda: fake

    http_response = await client.post("/api/v1/query", json={"question": _QUESTION})

    assert http_response.status_code == 200
    assert http_response.json()["status"] == "success"
    assert http_response.json()["original_question"] == _QUESTION


async def test_passes_the_question_through_unchanged(app: FastAPI, client: AsyncClient) -> None:
    fake = _FakeEngine(_make_success_response())
    app.dependency_overrides[get_query_mind_engine] = lambda: fake

    await client.post("/api/v1/query", json={"question": _QUESTION})

    assert fake.questions_asked == [_QUESTION]


async def test_an_empty_question_is_rejected_before_reaching_the_engine(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeEngine(_make_success_response())
    app.dependency_overrides[get_query_mind_engine] = lambda: fake

    response = await client.post("/api/v1/query", json={"question": ""})

    assert response.status_code == 422
    assert fake.questions_asked == []


async def test_a_failed_pipeline_run_still_returns_200(app: FastAPI, client: AsyncClient) -> None:
    failed = _make_success_response().model_copy(
        update={
            "status": PipelineStatus.FAILED,
            "error": "SQL generation failed.",
            "business_answer": None,
        }
    )
    app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine(failed)

    response = await client.post("/api/v1/query", json={"question": _QUESTION})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


async def test_records_the_pipeline_run_in_metrics(app: FastAPI, client: AsyncClient) -> None:
    fake = _FakeEngine(_make_success_response())
    collector = InMemoryMetricsCollector()
    app.dependency_overrides[get_query_mind_engine] = lambda: fake
    app.dependency_overrides[get_metrics_collector] = lambda: collector

    await client.post("/api/v1/query", json={"question": _QUESTION})

    snapshot = collector.snapshot()
    assert snapshot.pipeline_run_count == 1
    assert snapshot.pipeline_success_count == 1
