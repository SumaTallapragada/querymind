"""Tests for `querymind.sql_generation.engine.SQLGenerationEngine`."""

from __future__ import annotations

import pytest

from querymind.llm.exceptions import LLMPermanentError
from querymind.prompt_compiler.models import CompiledPrompt
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.engine import SQLGenerationEngine
from querymind.sql_generation.exceptions import SQLExtractionError
from querymind.sql_generation.models import ExtractionMethod, SQLStatementType

from .conftest import make_llm_adapter, make_llm_response


class TestGenerateHappyPath:
    def test_returns_the_extracted_and_normalized_sql(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        adapter = make_llm_adapter([make_llm_response(content="```sql\nSELECT 1\n```")])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.sql == "SELECT 1;"

    def test_detects_statement_type(self, compiled_prompt: CompiledPrompt) -> None:
        adapter = make_llm_adapter([make_llm_response(content="SELECT 1")])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.statement_type is SQLStatementType.SELECT

    def test_carries_dialect_from_the_compiled_prompt(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        prompt = compiled_prompt.model_copy(update={"dialect": SQLDialect.MYSQL})
        adapter = make_llm_adapter([make_llm_response(content="SELECT 1")])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(prompt)
        assert generated.dialect is SQLDialect.MYSQL

    def test_preserves_the_raw_llm_content_unmodified(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        raw = "Here you go:\n```sql\nSELECT 1\n```\nEnjoy!"
        adapter = make_llm_adapter([make_llm_response(content=raw)])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.raw_llm_content == raw

    def test_carries_the_llm_metrics_through(self, compiled_prompt: CompiledPrompt) -> None:
        response = make_llm_response(content="SELECT 1")
        adapter = make_llm_adapter([response])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.llm_metrics == response.metrics

    def test_statistics_reflect_the_extraction_and_normalization(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        adapter = make_llm_adapter([make_llm_response(content="```sql\nSELECT 1\n```")])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.statistics.extraction_method is ExtractionMethod.FENCED_SQL_BLOCK
        assert generated.statistics.raw_sql_length == len("SELECT 1")
        assert generated.statistics.normalized_sql_length == len("SELECT 1;")
        assert generated.statistics.normalization_changed_sql is True
        assert generated.statistics.generation_latency_ms >= 0.0

    def test_sends_the_compiled_prompt_to_the_llm_adapter(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        adapter = make_llm_adapter([make_llm_response(content="SELECT 1")])
        engine = SQLGenerationEngine(adapter)
        engine.generate(compiled_prompt)
        # Confirm the underlying provider actually received a request built from this prompt.
        sent_request = adapter._provider_client.requests[0]  # type: ignore[attr-defined]
        assert sent_request.prompt == compiled_prompt.as_text()


class TestGenerateExtractionFailure:
    def test_raises_sql_extraction_error_when_response_has_no_sql(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        adapter = make_llm_adapter([make_llm_response(content="   ")])
        engine = SQLGenerationEngine(adapter)
        with pytest.raises(SQLExtractionError):
            engine.generate(compiled_prompt)


class TestGeneratePropagatesLLMErrors:
    def test_propagates_llm_adapter_errors_untouched(self, compiled_prompt: CompiledPrompt) -> None:
        adapter = make_llm_adapter([LLMPermanentError("bad request")])
        engine = SQLGenerationEngine(adapter)
        with pytest.raises(LLMPermanentError):
            engine.generate(compiled_prompt)


class TestDependencyInjection:
    def test_default_collaborators_are_used_when_none_given(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        adapter = make_llm_adapter([make_llm_response(content="SELECT 1")])
        engine = SQLGenerationEngine(adapter)
        generated = engine.generate(compiled_prompt)
        assert generated.sql == "SELECT 1;"

    def test_accepts_a_custom_extractor_and_normalizer(
        self, compiled_prompt: CompiledPrompt
    ) -> None:
        from querymind.sql_generation.extractor import ExtractionResult, SQLExtractor
        from querymind.sql_generation.normalizer import SQLNormalizer

        class _UppercasingExtractor(SQLExtractor):
            def extract(self, raw_content: str) -> ExtractionResult:
                result = super().extract(raw_content)
                return ExtractionResult(sql=result.sql.upper(), method=result.method)

        class _NoOpNormalizer(SQLNormalizer):
            def normalize(self, sql: str) -> str:
                return sql

        adapter = make_llm_adapter([make_llm_response(content="select 1")])
        engine = SQLGenerationEngine(
            adapter, extractor=_UppercasingExtractor(), normalizer=_NoOpNormalizer()
        )
        generated = engine.generate(compiled_prompt)
        assert generated.sql == "SELECT 1"
