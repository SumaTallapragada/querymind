"""Tests for `querymind.sql_repair.serializer.SQLRepairSerializer`."""

from __future__ import annotations

import json

import yaml

from querymind.sql_repair.models import (
    RepairHistory,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)
from querymind.sql_repair.serializer import SQLRepairSerializer

from .conftest import make_generated_sql, make_validation_result


def _result() -> SQLRepairResult:
    generated = make_generated_sql("SELECT 1;")
    return SQLRepairResult(
        original_sql=generated,
        final_sql=generated,
        final_validation_result=make_validation_result(generated),
        history=RepairHistory(),
        statistics=RepairStatistics(
            attempt_count=0,
            successful_repairs=0,
            failed_repairs=0,
            repair_latency_ms=0.0,
            average_validation_latency_ms=0.0,
        ),
        status=RepairStatus.UNREPAIRABLE,
    )


class TestToDict:
    def test_returns_a_json_safe_dict(self) -> None:
        result = SQLRepairSerializer.to_dict(_result())
        assert isinstance(result, dict)
        assert result["status"] == "unrepairable"


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = SQLRepairSerializer.to_json(_result())
        parsed = json.loads(text)
        assert parsed["status"] == "unrepairable"


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = SQLRepairSerializer.to_yaml(_result())
        parsed = yaml.safe_load(text)
        assert parsed["status"] == "unrepairable"
