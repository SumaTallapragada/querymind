"""Tests for `querymind.prompt_compiler.cache`."""

from __future__ import annotations

from querymind.prompt_compiler.cache import InMemoryPromptCache, bundle_content_hash
from querymind.prompt_compiler.models import (
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptStatistics,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle

from .conftest import make_bundle, make_statistics


def _compiled_prompt() -> CompiledPrompt:
    return CompiledPrompt(
        system=SystemSection(content="sys", estimated_tokens=1),
        business_context=BusinessSection(content="biz", estimated_tokens=1),
        schema_context=SchemaSection(content="schema", estimated_tokens=1),
        relationships=RelationshipSection(content="rel", estimated_tokens=1),
        examples=ExampleSection(content="ex", estimated_tokens=1),
        constraints=ConstraintSection(content="con", estimated_tokens=1),
        output_format=OutputSection(content="out", estimated_tokens=1),
        statistics=PromptStatistics(
            estimated_total_tokens=7,
            section_token_usage=(),
            retrieved_example_count=0,
            schema_object_count=0,
            compilation_latency_ms=0.1,
        ),
        template_version="1.0.0",
        dialect=SQLDialect.POSTGRESQL,
    )


class TestBundleContentHash:
    def test_identical_bundles_hash_identically(self) -> None:
        assert bundle_content_hash(make_bundle()) == bundle_content_hash(make_bundle())

    def test_different_bundles_hash_differently(
        self, empty_bundle: RetrievedKnowledgeBundle
    ) -> None:
        assert bundle_content_hash(make_bundle()) != bundle_content_hash(empty_bundle)

    def test_ignores_statistics_so_latency_noise_does_not_break_caching(self) -> None:
        first = make_bundle(statistics=make_statistics(retrieval_latency_ms=1.0))
        second = make_bundle(statistics=make_statistics(retrieval_latency_ms=999.0))
        assert bundle_content_hash(first) == bundle_content_hash(second)


class TestInMemoryPromptCache:
    def test_returns_none_for_a_missing_key(self) -> None:
        cache = InMemoryPromptCache()
        assert cache.get(("h", "1.0.0", "postgresql")) is None

    def test_set_then_get_returns_the_stored_prompt(self) -> None:
        cache = InMemoryPromptCache()
        prompt = _compiled_prompt()
        key = ("h", "1.0.0", "postgresql")
        cache.set(key, prompt)
        assert cache.get(key) == prompt

    def test_clear_removes_every_entry(self) -> None:
        cache = InMemoryPromptCache()
        key = ("h", "1.0.0", "postgresql")
        cache.set(key, _compiled_prompt())
        cache.clear()
        assert cache.get(key) is None

    def test_distinct_keys_do_not_collide(self) -> None:
        cache = InMemoryPromptCache()
        prompt_a = _compiled_prompt()
        prompt_b = _compiled_prompt()
        cache.set(("h", "1.0.0", "postgresql"), prompt_a)
        cache.set(("h", "1.0.0", "mysql"), prompt_b)
        assert cache.get(("h", "1.0.0", "postgresql")) == prompt_a
        assert cache.get(("h", "1.0.0", "mysql")) == prompt_b
