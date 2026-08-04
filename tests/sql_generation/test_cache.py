"""Tests for `querymind.sql_generation.cache`."""

from __future__ import annotations

from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.cache import NoOpGeneratedSQLCache
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)


def _generated() -> GeneratedSQL:
    return GeneratedSQL(
        sql="SELECT 1;",
        statement_type=SQLStatementType.SELECT,
        raw_llm_content="SELECT 1",
        dialect=SQLDialect.POSTGRESQL,
        llm_metrics=GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=100.0,
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
        statistics=SQLGenerationStatistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql_length=8,
            normalized_sql_length=9,
            normalization_changed_sql=True,
            generation_latency_ms=1.0,
        ),
    )


class TestNoOpGeneratedSQLCache:
    def test_get_always_returns_none(self) -> None:
        cache = NoOpGeneratedSQLCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_get_return_it(self) -> None:
        cache = NoOpGeneratedSQLCache()
        cache.set("key", _generated())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        cache = NoOpGeneratedSQLCache()
        cache.clear()
