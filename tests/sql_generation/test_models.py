"""Tests for `querymind.sql_generation.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)


def _metrics() -> GenerationMetrics:
    return GenerationMetrics(
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-5",
        latency_ms=100.0,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        retry_count=0,
        finish_reason=FinishReason.COMPLETE,
    )


def _statistics(**overrides: object) -> SQLGenerationStatistics:
    defaults: dict[str, object] = {
        "extraction_method": ExtractionMethod.RAW_TEXT,
        "raw_sql_length": 9,
        "normalized_sql_length": 10,
        "normalization_changed_sql": True,
        "generation_latency_ms": 5.0,
    }
    defaults.update(overrides)
    return SQLGenerationStatistics(**defaults)  # type: ignore[arg-type]


def _generated(**overrides: object) -> GeneratedSQL:
    defaults: dict[str, object] = {
        "sql": "SELECT 1;",
        "statement_type": SQLStatementType.SELECT,
        "raw_llm_content": "SELECT 1",
        "dialect": SQLDialect.POSTGRESQL,
        "llm_metrics": _metrics(),
        "statistics": _statistics(),
    }
    defaults.update(overrides)
    return GeneratedSQL(**defaults)  # type: ignore[arg-type]


class TestSQLGenerationStatistics:
    def test_valid_construction(self) -> None:
        statistics = _statistics()
        assert statistics.extraction_method is ExtractionMethod.RAW_TEXT

    def test_rejects_negative_lengths(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(raw_sql_length=-1)

    def test_rejects_negative_latency(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(generation_latency_ms=-1.0)

    def test_is_frozen(self) -> None:
        statistics = _statistics()
        with pytest.raises(ValidationError):
            statistics.raw_sql_length = 100  # type: ignore[misc]


class TestGeneratedSQL:
    def test_valid_construction(self) -> None:
        generated = _generated()
        assert generated.sql == "SELECT 1;"
        assert generated.statement_type is SQLStatementType.SELECT
        assert generated.dialect is SQLDialect.POSTGRESQL

    def test_rejects_empty_sql(self) -> None:
        with pytest.raises(ValidationError):
            _generated(sql="")

    def test_is_frozen(self) -> None:
        generated = _generated()
        with pytest.raises(ValidationError):
            generated.sql = "SELECT 2;"  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GeneratedSQL(
                sql="SELECT 1;",
                statement_type=SQLStatementType.SELECT,
                raw_llm_content="SELECT 1",
                dialect=SQLDialect.POSTGRESQL,
                llm_metrics=_metrics(),
                statistics=_statistics(),
                bogus="nope",  # type: ignore[call-arg]
            )

    def test_llm_metrics_are_carried_through_unmodified(self) -> None:
        metrics = _metrics()
        generated = _generated(llm_metrics=metrics)
        assert generated.llm_metrics == metrics
