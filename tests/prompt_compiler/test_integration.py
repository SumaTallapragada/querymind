"""End-to-end tests against the real, fully wired pipeline.

Unlike the rest of this test package (a small synthetic
`RetrievedKnowledgeBundle` built for precise control), these tests
exercise `PromptCompiler` against the actual Metadata Engine -> Business
Knowledge Engine -> NLU -> Schema Linker -> Query Intelligence Library ->
Retrieval Engine -> Prompt Compiler chain, using the real data shipped
with QueryMind.
"""

from __future__ import annotations

from datetime import date

import pytest

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.models.base import Base
from querymind.nlu import QueryParser
from querymind.nlu.time import DefaultTimeExtractor
from querymind.prompt_compiler import PromptCompiler
from querymind.prompt_compiler.models import SectionName
from querymind.query_library import QueryLibraryRegistry
from querymind.query_library.models import SQLDialect
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker


@pytest.fixture(scope="module")
def retrieval_engine() -> RetrievalEngine:
    metadata_registry = MetadataRegistry(
        MetadataExtractor(Base.registry), ColumnDictionary.default()
    )
    metadata_registry.load()
    business_knowledge = BusinessKnowledgeRegistry()
    business_knowledge.load()
    query_library = QueryLibraryRegistry()
    query_library.load()
    return RetrievalEngine(query_library=query_library, business_knowledge=business_knowledge)


@pytest.fixture(scope="module")
def linker() -> SchemaLinker:
    metadata_registry = MetadataRegistry(
        MetadataExtractor(Base.registry), ColumnDictionary.default()
    )
    metadata_registry.load()
    return SchemaLinker(metadata_registry)


@pytest.fixture
def parser() -> QueryParser:
    return QueryParser(time_extractor=DefaultTimeExtractor(reference_date=date(2026, 8, 3)))


@pytest.fixture
def compiler() -> PromptCompiler:
    return PromptCompiler()


def test_top_customers_question_compiles_a_valid_prompt(
    retrieval_engine: RetrievalEngine,
    linker: SchemaLinker,
    parser: QueryParser,
    compiler: PromptCompiler,
) -> None:
    context = parser.parse("Who are our top 10 customers by revenue?")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=5)

    compiled = compiler.compile(bundle)

    assert compiled.dialect is SQLDialect.POSTGRESQL
    assert compiled.system.content.strip()
    assert compiled.constraints.content.strip()
    assert compiled.output_format.content.strip()
    assert "customers" in compiled.schema_context.content
    assert compiled.statistics.retrieved_example_count == len(bundle.retrieved_examples)


def test_compiled_prompt_renders_to_a_single_readable_text(
    retrieval_engine: RetrievalEngine,
    linker: SchemaLinker,
    parser: QueryParser,
    compiler: PromptCompiler,
) -> None:
    context = parser.parse("Which supplier has the highest lead time?")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=5)

    compiled = compiler.compile(bundle)
    text = compiled.as_text()

    assert "# System Instructions" in text
    assert "## Constraints" in text
    assert "## Output Format" in text
    assert text.index("# System Instructions") < text.index("## Output Format")


def test_repeated_compilation_of_the_same_question_hits_the_cache(
    retrieval_engine: RetrievalEngine,
    linker: SchemaLinker,
    parser: QueryParser,
    compiler: PromptCompiler,
) -> None:
    context = parser.parse("Show total revenue by product category.")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=5)

    first = compiler.compile(bundle)
    second = compiler.compile(bundle)
    assert first == second


def test_a_question_with_no_similar_examples_still_compiles_a_valid_prompt(
    retrieval_engine: RetrievalEngine,
    linker: SchemaLinker,
    parser: QueryParser,
    compiler: PromptCompiler,
) -> None:
    context = parser.parse("How many orders were placed in the last 30 days?")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=1)

    compiled = compiler.compile(bundle)
    assert compiled.examples.content.strip()
    names = {s.name for s in compiled.all_sections()}
    assert names == set(SectionName)


def test_dialect_flows_through_to_the_output_section(
    retrieval_engine: RetrievalEngine,
    linker: SchemaLinker,
    parser: QueryParser,
    compiler: PromptCompiler,
) -> None:
    context = parser.parse("What is the average review rating for each product?")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=3)

    compiled = compiler.compile(bundle, dialect=SQLDialect.MYSQL)
    assert "mysql" in compiled.output_format.content
