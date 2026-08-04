"""Tests for `querymind.sql_generation.formatter.GeneratedSQLFormatter`."""

from __future__ import annotations

from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.formatter import GeneratedSQLFormatter
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)


def _generated(**overrides: object) -> GeneratedSQL:
    defaults: dict[str, object] = {
        "sql": "SELECT 1;",
        "statement_type": SQLStatementType.SELECT,
        "raw_llm_content": "SELECT 1",
        "dialect": SQLDialect.POSTGRESQL,
        "llm_metrics": GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=123.4,
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
        "statistics": SQLGenerationStatistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql_length=8,
            normalized_sql_length=9,
            normalization_changed_sql=True,
            generation_latency_ms=5.0,
        ),
    }
    defaults.update(overrides)
    return GeneratedSQL(**defaults)  # type: ignore[arg-type]


class TestFormat:
    def test_includes_the_sql(self) -> None:
        text = GeneratedSQLFormatter().format(_generated())
        assert "SELECT 1;" in text

    def test_includes_dialect_and_statement_type(self) -> None:
        text = GeneratedSQLFormatter().format(_generated())
        assert "dialect: postgresql" in text
        assert "statement: select" in text

    def test_includes_token_usage(self) -> None:
        text = GeneratedSQLFormatter().format(_generated())
        assert "100 in / 20 out" in text

    def test_includes_latency(self) -> None:
        text = GeneratedSQLFormatter().format(_generated())
        assert "123.4ms" in text

    def test_sql_appears_after_the_header(self) -> None:
        text = GeneratedSQLFormatter().format(_generated())
        assert text.index("--") < text.index("SELECT 1;")
