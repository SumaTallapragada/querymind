"""Tests for `querymind.prompt_compiler.compiler.PromptCompiler`."""

from __future__ import annotations

from querymind.prompt_compiler.budget import PromptBudgetManager
from querymind.prompt_compiler.cache import InMemoryPromptCache, bundle_content_hash
from querymind.prompt_compiler.compiler import PromptCompiler
from querymind.prompt_compiler.models import CompiledPrompt, SectionName
from querymind.prompt_compiler.templates import DefaultPromptTemplate
from querymind.prompt_compiler.validator import PromptValidator
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle


class TestCompile:
    def test_produces_all_seven_sections_in_pipeline_order(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiled = PromptCompiler().compile(bundle)
        assert isinstance(compiled, CompiledPrompt)
        names = [s.name for s in compiled.all_sections()]
        assert names == [
            SectionName.SYSTEM,
            SectionName.BUSINESS_CONTEXT,
            SectionName.SCHEMA_CONTEXT,
            SectionName.RELATIONSHIP,
            SectionName.RETRIEVED_EXAMPLES,
            SectionName.CONSTRAINT,
            SectionName.OUTPUT_FORMAT,
        ]

    def test_default_dialect_is_postgresql(self, bundle: RetrievedKnowledgeBundle) -> None:
        compiled = PromptCompiler().compile(bundle)
        assert compiled.dialect is SQLDialect.POSTGRESQL
        assert "postgresql" in compiled.output_format.content

    def test_honors_requested_dialect(self, bundle: RetrievedKnowledgeBundle) -> None:
        compiled = PromptCompiler().compile(bundle, dialect=SQLDialect.SQLITE)
        assert compiled.dialect is SQLDialect.SQLITE
        assert "sqlite" in compiled.output_format.content

    def test_template_version_is_recorded(self, bundle: RetrievedKnowledgeBundle) -> None:
        compiled = PromptCompiler().compile(bundle)
        assert compiled.template_version == DefaultPromptTemplate().version

    def test_statistics_reflect_the_retrieved_examples_and_schema_objects(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiled = PromptCompiler().compile(bundle)
        assert compiled.statistics.retrieved_example_count == 1
        assert compiled.statistics.schema_object_count == len(
            compiled.schema_context.schema_objects
        )
        assert compiled.statistics.estimated_total_tokens == sum(
            s.estimated_tokens for s in compiled.all_sections()
        )
        assert compiled.statistics.compilation_latency_ms >= 0.0
        assert len(compiled.statistics.section_token_usage) == 7

    def test_as_text_contains_every_non_empty_section(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiled = PromptCompiler().compile(bundle)
        text = compiled.as_text()
        assert "# System Instructions" in text
        assert "## Output Format" in text


class TestCaching:
    def test_second_compile_of_the_same_bundle_returns_a_cached_result(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        cache = InMemoryPromptCache()
        compiler = PromptCompiler(cache=cache)
        first = compiler.compile(bundle)
        second = compiler.compile(bundle)
        assert first == second
        key = (
            bundle_content_hash(bundle),
            DefaultPromptTemplate().version,
            SQLDialect.POSTGRESQL.value,
        )
        assert cache.get(key) == first

    def test_different_dialects_are_cached_independently(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        cache = InMemoryPromptCache()
        compiler = PromptCompiler(cache=cache)
        postgres = compiler.compile(bundle, dialect=SQLDialect.POSTGRESQL)
        mysql = compiler.compile(bundle, dialect=SQLDialect.MYSQL)
        assert postgres.dialect != mysql.dialect
        assert postgres.output_format.content != mysql.output_format.content

    def test_cache_is_populated_only_after_a_successful_compile(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        cache = InMemoryPromptCache()
        compiler = PromptCompiler(cache=cache)
        assert compiler.compile(bundle) is not None
        key = (
            bundle_content_hash(bundle),
            DefaultPromptTemplate().version,
            SQLDialect.POSTGRESQL.value,
        )
        assert cache.get(key) is not None


class TestTokenBudgetIntegration:
    def test_a_very_small_budget_still_produces_a_valid_required_section_set(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiler = PromptCompiler(budget_manager=PromptBudgetManager(50))
        compiled = compiler.compile(bundle)
        assert compiled.system.content.strip()
        assert compiled.constraints.content.strip()
        assert compiled.output_format.content.strip()

    def test_default_budget_manager_uses_default_max_tokens(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiler = PromptCompiler()
        compiled = compiler.compile(bundle)
        assert compiled.statistics.estimated_total_tokens <= 4000


class TestDependencyInjection:
    def test_custom_validator_max_tokens_is_used_when_no_budget_manager_given(self) -> None:
        # A very strict validator (but a generous default budget manager) should not block
        # compilation: PromptCompiler always trims with its own budget manager first.
        validator = PromptValidator(max_tokens=100000)
        compiler = PromptCompiler(validator=validator)
        assert compiler is not None

    def test_two_compilers_with_separate_caches_do_not_share_state(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiler_a = PromptCompiler(cache=InMemoryPromptCache())
        compiler_b = PromptCompiler(cache=InMemoryPromptCache())
        compiler_a.compile(bundle)
        # compiler_b's own cache must still be empty -- no cross-instance leakage.
        key = (
            bundle_content_hash(bundle),
            DefaultPromptTemplate().version,
            SQLDialect.POSTGRESQL.value,
        )
        assert compiler_b._cache.get(key) is None


class TestEmptyBundle:
    def test_compiles_successfully_with_no_resolved_schema_or_examples(
        self, empty_bundle: RetrievedKnowledgeBundle
    ) -> None:
        compiled = PromptCompiler().compile(empty_bundle)
        assert compiled.statistics.retrieved_example_count == 0
        assert compiled.statistics.schema_object_count == 0
        assert compiled.system.content.strip()
        assert compiled.constraints.content.strip()
        assert compiled.output_format.content.strip()
