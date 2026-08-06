"""Tests for `querymind.orchestrator.serializer.QueryMindSerializer`."""

from __future__ import annotations

import json

import yaml

from querymind.orchestrator.models import PipelineStatistics, PipelineStatus, QueryMindResponse
from querymind.orchestrator.serializer import QueryMindSerializer

from .conftest import (
    make_business_answer,
    make_execution_result,
    make_generated_sql,
    make_validation_result,
)


def _response() -> QueryMindResponse:
    generated = make_generated_sql("SELECT customer_id FROM customers;")
    execution = make_execution_result(generated)
    return QueryMindResponse(
        original_question="Who are our customers?",
        business_answer=make_business_answer(execution),
        generated_sql=generated,
        validation_result=make_validation_result(generated),
        repair_result=None,
        execution_result=execution,
        statistics=PipelineStatistics(
            total_latency_ms=12.5, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
        status=PipelineStatus.SUCCESS,
        error=None,
    )


class TestToDict:
    def test_returns_json_safe_primitives(self) -> None:
        data = QueryMindSerializer.to_dict(_response())
        assert data["status"] == "success"
        assert data["original_question"] == "Who are our customers?"
        assert isinstance(data["statistics"]["stage_timings"], list)


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = QueryMindSerializer.to_json(_response())
        parsed = json.loads(text)
        assert parsed["status"] == "success"
        assert parsed["generated_sql"]["sql"] == "SELECT customer_id FROM customers;"

    def test_indent_is_honored(self) -> None:
        text = QueryMindSerializer.to_json(_response(), indent=None)
        assert "\n" not in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = QueryMindSerializer.to_yaml(_response())
        parsed = yaml.safe_load(text)
        assert parsed["status"] == "success"
