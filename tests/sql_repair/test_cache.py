"""Tests for `querymind.sql_repair.cache`."""

from __future__ import annotations

from querymind.sql_repair.cache import NoOpSQLRepairCache
from querymind.sql_repair.models import (
    RepairHistory,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)

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


class TestNoOpSQLRepairCache:
    def test_get_always_returns_none(self) -> None:
        cache = NoOpSQLRepairCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_get_return_it(self) -> None:
        cache = NoOpSQLRepairCache()
        cache.set("key", _result())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        NoOpSQLRepairCache().clear()
