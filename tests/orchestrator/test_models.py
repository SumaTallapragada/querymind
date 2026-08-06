"""Tests for `querymind.orchestrator.models` — immutability and validation constraints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
    StageTiming,
)

from .conftest import (
    make_business_answer,
    make_execution_result,
    make_generated_sql,
    make_validation_result,
)


def _statistics(**overrides: object) -> PipelineStatistics:
    defaults: dict[str, object] = {
        "total_latency_ms": 100.0,
        "stage_timings": (StageTiming(stage=PipelineStage.NLU, latency_ms=1.0),),
        "repair_attempted": False,
        "repair_performed": False,
    }
    defaults.update(overrides)
    return PipelineStatistics(**defaults)  # type: ignore[arg-type]


class TestStageTiming:
    def test_is_frozen(self) -> None:
        timing = StageTiming(stage=PipelineStage.NLU, latency_ms=1.0)
        with pytest.raises(ValidationError):
            timing.latency_ms = 2.0  # type: ignore[misc]

    def test_negative_latency_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StageTiming(stage=PipelineStage.NLU, latency_ms=-1.0)


class TestPipelineStage:
    def test_has_the_eleven_required_members(self) -> None:
        assert {member.value for member in PipelineStage} == {
            "nlu",
            "schema_linking",
            "business_knowledge",
            "retrieval",
            "prompt_compilation",
            "llm",
            "sql_generation",
            "sql_validation",
            "sql_repair",
            "sql_execution",
            "result_formatting",
        }


class TestPipelineStatistics:
    def test_negative_total_latency_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(total_latency_ms=-1.0)

    def test_stage_timings_is_a_tuple(self) -> None:
        stats = _statistics()
        assert isinstance(stats.stage_timings, tuple)

    def test_is_frozen(self) -> None:
        stats = _statistics()
        with pytest.raises(ValidationError):
            stats.repair_attempted = True  # type: ignore[misc]


class TestQueryMindResponse:
    def test_a_minimal_failed_response_needs_no_optional_fields(self) -> None:
        response = QueryMindResponse(
            original_question="Who are our top customers?",
            statistics=_statistics(),
            status=PipelineStatus.FAILED,
            error="Something went wrong.",
        )
        assert response.business_answer is None
        assert response.generated_sql is None
        assert response.validation_result is None
        assert response.repair_result is None
        assert response.execution_result is None

    def test_a_success_response_carries_every_reused_phase_model(self) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        validation = make_validation_result(generated)
        execution = make_execution_result(generated)
        answer = make_business_answer(execution)

        response = QueryMindResponse(
            original_question="Who are our customers?",
            business_answer=answer,
            generated_sql=generated,
            validation_result=validation,
            repair_result=None,
            execution_result=execution,
            statistics=_statistics(),
            status=PipelineStatus.SUCCESS,
            error=None,
        )
        assert response.business_answer is answer
        assert response.generated_sql is generated
        assert response.execution_result is execution

    def test_is_frozen(self) -> None:
        response = QueryMindResponse(
            original_question="q", statistics=_statistics(), status=PipelineStatus.FAILED, error="x"
        )
        with pytest.raises(ValidationError):
            response.status = PipelineStatus.SUCCESS  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            QueryMindResponse(  # type: ignore[call-arg]
                original_question="q",
                statistics=_statistics(),
                status=PipelineStatus.FAILED,
                error="x",
                unexpected="value",
            )
