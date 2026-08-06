"""Tests for `querymind.orchestrator.engine.QueryMindEngine` — the never-throws public entry point.

Wraps a small fake `PipelineRunner` (a `.run` coroutine returning a
canned outcome or raising) -- `QueryMindEngine`'s own responsibility
under test is exactly the try/except conversion into a `QueryMindResponse`,
not `PipelineRunner`'s sequencing logic, which `test_pipeline.py` already
covers.
"""

from __future__ import annotations

from querymind.orchestrator.engine import QueryMindEngine
from querymind.orchestrator.exceptions import PipelineExecutionError
from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
    StageTiming,
)

from .conftest import make_execution_result, make_generated_sql, make_validation_result


class _FakeRunner:
    def __init__(self, outcome: QueryMindResponse | Exception) -> None:
        self._outcome = outcome

    async def run(self, question: str) -> QueryMindResponse:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _success_response(question: str) -> QueryMindResponse:
    return QueryMindResponse(
        original_question=question,
        statistics=PipelineStatistics(
            total_latency_ms=5.0,
            stage_timings=(StageTiming(stage=PipelineStage.NLU, latency_ms=1.0),),
            repair_attempted=False,
            repair_performed=False,
        ),
        status=PipelineStatus.SUCCESS,
        error=None,
    )


class TestAskSuccess:
    async def test_returns_the_pipeline_runners_response_unchanged(self) -> None:
        expected = _success_response("Who are our top customers?")
        engine = QueryMindEngine(_FakeRunner(expected))  # type: ignore[arg-type]
        response = await engine.ask("Who are our top customers?")
        assert response is expected


class TestAskConvertsPipelineExecutionError:
    async def test_populates_status_error_and_statistics_from_the_exception(self) -> None:
        timings = (StageTiming(stage=PipelineStage.NLU, latency_ms=1.0),)
        cause = RuntimeError("LLM retry exhausted")
        error = PipelineExecutionError(
            "Pipeline failed at stage 'sql_generation': LLM retry exhausted",
            stage=PipelineStage.SQL_GENERATION,
            stage_timings=timings,
            repair_attempted=False,
            repair_performed=False,
            generated_sql=None,
            validation_result=None,
            repair_result=None,
            execution_result=None,
        )
        error.__cause__ = cause

        engine = QueryMindEngine(_FakeRunner(error))  # type: ignore[arg-type]
        response = await engine.ask("Who are our top customers?")

        assert response.status is PipelineStatus.FAILED
        assert response.error == "LLM retry exhausted"
        assert response.statistics.stage_timings == timings
        assert response.business_answer is None
        assert response.generated_sql is None

    async def test_falls_back_to_the_errors_own_message_without_a_cause(self) -> None:
        error = PipelineExecutionError(
            "Pipeline failed at stage 'nlu': boom",
            stage=PipelineStage.NLU,
            stage_timings=(),
            repair_attempted=False,
            repair_performed=False,
            generated_sql=None,
            validation_result=None,
            repair_result=None,
            execution_result=None,
        )
        engine = QueryMindEngine(_FakeRunner(error))  # type: ignore[arg-type]
        response = await engine.ask("q")
        assert response.error == "Pipeline failed at stage 'nlu': boom"

    async def test_carries_partial_execution_result_through_to_the_response(self) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        execution = make_execution_result(generated)
        error = PipelineExecutionError(
            "boom",
            stage=PipelineStage.RESULT_FORMATTING,
            stage_timings=(),
            repair_attempted=False,
            repair_performed=False,
            generated_sql=generated,
            validation_result=make_validation_result(generated),
            repair_result=None,
            execution_result=execution,
        )
        engine = QueryMindEngine(_FakeRunner(error))  # type: ignore[arg-type]
        response = await engine.ask("q")
        assert response.execution_result is execution
        assert response.generated_sql is generated


class TestAskNeverThrows:
    async def test_a_genuinely_unexpected_exception_still_becomes_a_failed_response(self) -> None:
        engine = QueryMindEngine(_FakeRunner(RuntimeError("something nobody expected")))  # type: ignore[arg-type]
        response = await engine.ask("Who are our top customers?")

        assert response.status is PipelineStatus.FAILED
        assert response.error == "something nobody expected"
        assert response.statistics.stage_timings == ()
        assert response.statistics.repair_attempted is False

    async def test_original_question_is_preserved_even_on_failure(self) -> None:
        engine = QueryMindEngine(_FakeRunner(RuntimeError("boom")))  # type: ignore[arg-type]
        response = await engine.ask("What is our total revenue?")
        assert response.original_question == "What is our total revenue?"
