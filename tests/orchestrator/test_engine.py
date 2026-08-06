"""Tests for `querymind.orchestrator.engine.QueryMindEngine` — the never-throws public entry point.

Wraps a small fake `PipelineRunner` (a `.run` coroutine returning a
canned outcome or raising) -- `QueryMindEngine`'s own responsibility
under test is exactly the try/except conversion into a `QueryMindResponse`,
not `PipelineRunner`'s sequencing logic, which `test_pipeline.py` already
covers.
"""

from __future__ import annotations

from typing import Any

import pytest

from querymind.orchestrator.engine import QueryMindEngine
from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.exceptions import PipelineExecutionError
from querymind.orchestrator.models import (
    GeneratedSqlResult,
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
    StageTiming,
)
from querymind.sql_repair.models import SQLRepairResult
from querymind.sql_validation.models import SQLValidationResult

from .conftest import (
    make_execution_result,
    make_generated_sql,
    make_repair_result,
    make_validation_result,
)


class _FakeRunner:
    def __init__(
        self,
        outcome: QueryMindResponse | Exception,
        generate_sql_outcome: GeneratedSqlResult | Exception | None = None,
        repair_sql_outcome: SQLRepairResult | Exception | None = None,
    ) -> None:
        self._outcome = outcome
        self._generate_sql_outcome = generate_sql_outcome
        self._repair_sql_outcome = repair_sql_outcome
        self.received_event_publisher: StageEventPublisher | None = None

    async def run(
        self, question: str, *, event_publisher: StageEventPublisher | None = None
    ) -> QueryMindResponse:
        self.received_event_publisher = event_publisher
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def generate_sql(self, question: str) -> GeneratedSqlResult:
        if isinstance(self._generate_sql_outcome, Exception):
            raise self._generate_sql_outcome
        assert self._generate_sql_outcome is not None
        return self._generate_sql_outcome

    async def repair_sql(self, question: str, validation_result: SQLValidationResult) -> Any:
        if isinstance(self._repair_sql_outcome, Exception):
            raise self._repair_sql_outcome
        return self._repair_sql_outcome


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

    async def test_omitting_event_publisher_passes_none_through(self) -> None:
        runner = _FakeRunner(_success_response("q"))
        engine = QueryMindEngine(runner)  # type: ignore[arg-type]
        await engine.ask("q")
        assert runner.received_event_publisher is None

    async def test_an_event_publisher_is_passed_through_to_the_runner(self) -> None:
        runner = _FakeRunner(_success_response("q"))
        engine = QueryMindEngine(runner)  # type: ignore[arg-type]
        publisher = object()
        await engine.ask("q", event_publisher=publisher)  # type: ignore[arg-type]
        assert runner.received_event_publisher is publisher


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


class TestAskForSql:
    async def test_delegates_to_the_pipeline_runners_generate_sql(self) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        expected = GeneratedSqlResult(
            original_question="q",
            generated_sql=generated,
            validation_result=make_validation_result(generated),
            repair_result=None,
            statistics=PipelineStatistics(
                total_latency_ms=1.0,
                stage_timings=(),
                repair_attempted=False,
                repair_performed=False,
            ),
        )
        engine = QueryMindEngine(_FakeRunner(RuntimeError("unused"), generate_sql_outcome=expected))  # type: ignore[arg-type]
        result = await engine.ask_for_sql("q")
        assert result is expected

    async def test_does_not_catch_pipeline_execution_error(self) -> None:
        error = PipelineExecutionError(
            "boom",
            stage=PipelineStage.SQL_GENERATION,
            stage_timings=(),
            repair_attempted=False,
            repair_performed=False,
            generated_sql=None,
            validation_result=None,
            repair_result=None,
            execution_result=None,
        )
        engine = QueryMindEngine(_FakeRunner(RuntimeError("unused"), generate_sql_outcome=error))  # type: ignore[arg-type]
        with pytest.raises(PipelineExecutionError):
            await engine.ask_for_sql("q")


class TestRepair:
    async def test_delegates_to_the_pipeline_runners_repair_sql(self) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        validation_result = make_validation_result(generated)
        expected = make_repair_result(generated, generated, validation_result)
        engine = QueryMindEngine(
            _FakeRunner(RuntimeError("unused"), repair_sql_outcome=expected)  # type: ignore[arg-type]
        )
        result = await engine.repair("q", validation_result)
        assert result is expected

    async def test_propagates_a_genuine_failure(self) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        validation_result = make_validation_result(generated)
        engine = QueryMindEngine(
            _FakeRunner(  # type: ignore[arg-type]
                RuntimeError("unused"), repair_sql_outcome=RuntimeError("retrieval failed")
            )
        )
        with pytest.raises(RuntimeError, match="retrieval failed"):
            await engine.repair("q", validation_result)
