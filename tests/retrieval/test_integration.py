"""End-to-end tests against the real, fully wired pipeline.

Unlike the rest of this test package (a small synthetic `LinkedQueryContext`
and library built for precise control), these tests exercise
`RetrievalEngine` against the actual `QueryParser` -> `SchemaLinker` ->
`RetrievalEngine` chain, using the real Metadata Engine, Business
Knowledge Engine, and Query Intelligence Library shipped with QueryMind.
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
from querymind.query_library import QueryLibraryRegistry
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker


@pytest.fixture(scope="module")
def engine() -> RetrievalEngine:
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


def test_top_customers_question_retrieves_the_matching_example(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("Who are our top 10 customers by revenue?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked, top_k=5)
    assert bundle.retrieved_examples
    assert bundle.retrieved_examples[0].example.id == "top_customers_by_revenue"


def test_supplier_lead_time_question_retrieves_the_matching_example(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("Which supplier has the highest lead time?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked, top_k=5)
    assert bundle.retrieved_examples[0].example.id == "supplier_longest_lead_time"
    assert "lead_time" in bundle.retrieved_examples[0].matched_business_concepts


def test_revenue_by_category_question_retrieves_the_matching_example(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("Show total revenue by product category.")
    linked = linker.link(context)
    bundle = engine.retrieve(linked, top_k=5)
    assert bundle.retrieved_examples[0].example.id == "revenue_by_category"


def test_default_top_k_is_five(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("How many orders were placed in the last 30 days?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked)
    assert bundle.statistics.top_k == 5
    assert len(bundle.retrieved_examples) == 5


def test_every_retrieved_example_has_a_non_empty_explanation(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("What is the average review rating for each product?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked, top_k=3)
    for retrieved in bundle.retrieved_examples:
        assert retrieved.selection_explanation.strip()


def test_statistics_candidate_count_matches_the_full_library_size(
    engine: RetrievalEngine, linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("How many customers do we have?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked)
    assert bundle.statistics.candidate_count == 25


def test_works_without_business_knowledge_injected(
    linker: SchemaLinker, parser: QueryParser
) -> None:
    """business_knowledge is optional — retrieval must still work with plain string comparison."""
    query_library = QueryLibraryRegistry()
    query_library.load()
    engine = RetrievalEngine(query_library=query_library)  # no business_knowledge

    context = parser.parse("Who are our top 10 customers by revenue?")
    linked = linker.link(context)
    bundle = engine.retrieve(linked, top_k=3)
    assert bundle.retrieved_examples
