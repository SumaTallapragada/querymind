"""Tests for `querymind.sql_repair.parser.RepairedSQLExtractor`."""

from __future__ import annotations

import pytest

from querymind.query_library.models import SQLDialect
from querymind.sql_generation.models import ExtractionMethod, SQLStatementType
from querymind.sql_repair.exceptions import RepairedSQLExtractionError
from querymind.sql_repair.parser import RepairedSQLExtractor

from .conftest import make_llm_response


class TestExtractSuccess:
    def test_extracts_a_fenced_sql_block(self) -> None:
        response = make_llm_response(content="```sql\nSELECT 1\n```")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.sql == "SELECT 1;"

    def test_extracts_plain_unfenced_sql(self) -> None:
        response = make_llm_response(content="SELECT 1")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.sql == "SELECT 1;"

    def test_detects_statement_type(self) -> None:
        response = make_llm_response(content="SELECT 1")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.statement_type is SQLStatementType.SELECT

    def test_preserves_raw_llm_content(self) -> None:
        raw = "Here you go:\n```sql\nSELECT 1\n```"
        response = make_llm_response(content=raw)
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.raw_llm_content == raw

    def test_carries_the_llm_metrics_through(self) -> None:
        response = make_llm_response(content="SELECT 1")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.llm_metrics == response.metrics

    def test_uses_the_given_dialect(self) -> None:
        response = make_llm_response(content="SELECT 1")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.MYSQL)
        assert generated.dialect is SQLDialect.MYSQL

    def test_statistics_reflect_extraction_method(self) -> None:
        response = make_llm_response(content="```sql\nSELECT 1\n```")
        generated = RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
        assert generated.statistics.extraction_method is ExtractionMethod.FENCED_SQL_BLOCK


class TestExtractFailure:
    def test_raises_repaired_sql_extraction_error_on_empty_response(self) -> None:
        response = make_llm_response(content="   ")
        with pytest.raises(RepairedSQLExtractionError):
            RepairedSQLExtractor().extract(response, dialect=SQLDialect.POSTGRESQL)
