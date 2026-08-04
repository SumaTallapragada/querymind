"""Tests for `querymind.sql_validation.cache`."""

from __future__ import annotations

from querymind.sql_validation.cache import NoOpSQLValidationCache
from querymind.sql_validation.models import SQLValidationResult, ValidationStatistics

from .conftest import make_generated_sql


def _result() -> SQLValidationResult:
    return SQLValidationResult(
        generated_sql=make_generated_sql("SELECT 1;"),
        is_valid=True,
        validation_statistics=ValidationStatistics(
            validation_latency_ms=1.0,
            table_count=0,
            column_count=0,
            join_count=0,
            function_count=0,
            error_count=0,
            warning_count=0,
        ),
    )


class TestNoOpSQLValidationCache:
    def test_get_always_returns_none(self) -> None:
        cache = NoOpSQLValidationCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_get_return_it(self) -> None:
        cache = NoOpSQLValidationCache()
        cache.set("key", _result())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        NoOpSQLValidationCache().clear()
