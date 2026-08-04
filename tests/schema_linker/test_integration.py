"""End-to-end tests against the real QueryMind schema and business dictionary.

Unlike the rest of this test package (a small synthetic schema built for
precise control), these tests exercise `SchemaLinker` against the actual
`MetadataRegistry` built from `querymind.models` + the shipped
dictionary — the same combination `querymind.nlu.QueryParser` output is
meant to be linked against in practice. Locks in real, observed behavior
on real ambiguity and gap cases discovered while building this package.
"""

from __future__ import annotations

from datetime import date

import pytest

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.models.base import Base
from querymind.nlu import QueryParser
from querymind.nlu.time import DefaultTimeExtractor
from querymind.schema_linker.linker import SchemaLinker
from querymind.schema_linker.models import ConceptKind, MatchTier


@pytest.fixture(scope="module")
def real_registry() -> MetadataRegistry:
    registry = MetadataRegistry(MetadataExtractor(Base.registry), ColumnDictionary.default())
    registry.load()
    return registry


@pytest.fixture
def linker(real_registry: MetadataRegistry) -> SchemaLinker:
    return SchemaLinker(real_registry)


@pytest.fixture
def parser() -> QueryParser:
    return QueryParser(time_extractor=DefaultTimeExtractor(reference_date=date(2026, 8, 3)))


def test_customer_entity_resolves_exactly(linker: SchemaLinker, parser: QueryParser) -> None:
    context = parser.parse("Show me the top 10 customers by revenue")
    linked = linker.link(context)
    assert linked.primary_entity is not None
    assert linked.primary_entity.table.name == "customers"
    assert linked.primary_entity.matching_reason is MatchTier.EXACT


def test_price_filter_resolves_to_products_unit_price(
    linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("List the products with price greater than 500")
    linked = linker.link(context)
    assert len(linked.filters) == 1
    assert linked.filters[0].column.table_name == "products"
    assert linked.filters[0].column.name == "unit_price"
    assert linked.is_fully_resolved is True


def test_category_filter_joins_products_to_product_categories(
    linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("Show products where category equals electronics")
    linked = linker.link(context)
    assert linked.primary_entity is not None
    assert linked.primary_entity.table.name == "products"
    assert len(linked.filters) == 1
    assert linked.filters[0].column.table_name == "product_categories"
    assert len(linked.relationship_paths) == 1
    assert {
        linked.relationship_paths[0].source_table,
        linked.relationship_paths[0].target_table,
    } == {
        "products",
        "product_categories",
    }


def test_revenue_has_no_match_in_the_real_dictionary(
    linker: SchemaLinker, parser: QueryParser
) -> None:
    """`orders.total_amount`'s synonyms are "order total"/"amount charged"/"grand total" — never
    "revenue" — so this must come back unresolved rather than an incorrect silent guess."""
    context = parser.parse("What is the total revenue this month?")
    linked = linker.link(context)
    assert linked.metrics == ()
    assert linked.is_fully_resolved is False
    revenue_ambiguities = [a for a in linked.ambiguities if a.business_concept == "revenue"]
    assert len(revenue_ambiguities) == 1
    assert revenue_ambiguities[0].concept_kind is ConceptKind.METRIC
    assert revenue_ambiguities[0].candidates == ()


def test_country_dimension_is_genuinely_ambiguous_across_tables(
    real_registry: MetadataRegistry,
) -> None:
    """`country_code` exists, with an identical business-dictionary label, on three unrelated
    tables (customer_addresses, suppliers, warehouses) — none should be silently preferred."""
    from querymind.schema_linker.resolver import ConceptResolver

    resolver = ConceptResolver(real_registry)
    resolved, ambiguity = resolver.resolve_dimension("country")
    assert resolved is None
    assert ambiguity is not None
    matched_tables = {c.table_name for c in ambiguity.candidates if c.confidence >= 0.9}
    assert matched_tables == {"customer_addresses", "suppliers", "warehouses"}


def test_supplier_lead_time_resolves_and_carries_max_aggregation(
    linker: SchemaLinker, parser: QueryParser
) -> None:
    context = parser.parse("Which supplier has the highest lead time?")
    linked = linker.link(context)
    assert linked.primary_entity is not None
    assert linked.primary_entity.table.name == "suppliers"
    assert len(linked.metrics) == 1
    assert linked.metrics[0].column.name == "lead_time_days"
    assert linked.is_fully_resolved is True
