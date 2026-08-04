"""Tests for the seven section builders in `querymind.prompt_compiler.sections`."""

from __future__ import annotations

from querymind.prompt_compiler.models import (
    BusinessSection,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.prompt_compiler.sections import (
    BusinessSectionBuilder,
    ConstraintSectionBuilder,
    ExampleSectionBuilder,
    OutputSectionBuilder,
    RelationshipSectionBuilder,
    SchemaSectionBuilder,
    SystemSectionBuilder,
)
from querymind.prompt_compiler.templates import CONSTRAINT_RULES, SYSTEM_PREAMBLE
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle

from .conftest import make_bundle


class TestSystemSectionBuilder:
    def test_returns_the_fixed_system_preamble(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = SystemSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, SystemSection)
        assert section.content == SYSTEM_PREAMBLE
        assert section.estimated_tokens > 0

    def test_ignores_bundle_content(self, empty_bundle: RetrievedKnowledgeBundle) -> None:
        section = SystemSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert section.content == SYSTEM_PREAMBLE


class TestBusinessSectionBuilder:
    def test_lists_business_concepts(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = BusinessSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, BusinessSection)
        assert "customer" in section.content
        assert "revenue" in section.content

    def test_empty_when_no_business_concepts(self, empty_bundle: RetrievedKnowledgeBundle) -> None:
        section = BusinessSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert "No specific business concepts" in section.content


class TestSchemaSectionBuilder:
    def test_lists_resolved_tables_and_columns(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = SchemaSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, SchemaSection)
        assert "customers" in section.schema_objects
        assert "orders" in section.schema_objects
        assert "orders.total_amount" in section.schema_objects
        assert "Table `customers`" in section.content
        assert "Column `orders.total_amount`" in section.content

    def test_deduplicates_repeated_tables_and_columns(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        # primary_entity=customers, secondary_entities=(orders,); metrics reference orders too.
        section = SchemaSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert section.schema_objects.count("orders") == 1

    def test_placeholder_when_nothing_resolved(
        self, empty_bundle: RetrievedKnowledgeBundle
    ) -> None:
        section = SchemaSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert section.schema_objects == ()
        assert "No schema objects were resolved" in section.content


class TestRelationshipSectionBuilder:
    def test_lists_relationship_paths(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = RelationshipSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, RelationshipSection)
        assert "orders.customer_id" in section.content
        assert "customers.customer_id" in section.content
        assert "via `customer`" in section.content

    def test_placeholder_when_no_relationships(
        self, empty_bundle: RetrievedKnowledgeBundle
    ) -> None:
        section = RelationshipSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert "No table joins are required" in section.content


class TestExampleSectionBuilder:
    def test_renders_one_block_per_retrieved_example(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        section = ExampleSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, ExampleSection)
        assert section.example_ids == ("top_customers_by_revenue",)
        assert "Example 1: Top 10 Customers by Revenue" in section.content
        assert "SELECT c.customer_id" in section.content

    def test_preserves_retrieval_order_in_example_ids(self) -> None:
        from .conftest import make_example, make_retrieved_example

        first = make_retrieved_example(example=make_example(id="a"))
        second = make_retrieved_example(example=make_example(id="b"))
        bundle = make_bundle(retrieved_examples=(first, second))
        section = ExampleSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert section.example_ids == ("a", "b")

    def test_placeholder_when_no_examples(self, empty_bundle: RetrievedKnowledgeBundle) -> None:
        section = ExampleSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert section.example_ids == ()
        assert "No similar example questions" in section.content


class TestConstraintSectionBuilder:
    def test_renders_every_constraint_rule(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = ConstraintSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        assert isinstance(section, ConstraintSection)
        for rule in CONSTRAINT_RULES:
            assert rule in section.content

    def test_ignores_bundle_content(self, empty_bundle: RetrievedKnowledgeBundle) -> None:
        full = ConstraintSectionBuilder().build(make_bundle(), SQLDialect.POSTGRESQL)
        empty = ConstraintSectionBuilder().build(empty_bundle, SQLDialect.POSTGRESQL)
        assert full.content == empty.content


class TestOutputSectionBuilder:
    def test_parameterizes_by_dialect(self, bundle: RetrievedKnowledgeBundle) -> None:
        section = OutputSectionBuilder().build(bundle, SQLDialect.MYSQL)
        assert isinstance(section, OutputSection)
        assert "mysql" in section.content

    def test_different_dialects_produce_different_content(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        postgres = OutputSectionBuilder().build(bundle, SQLDialect.POSTGRESQL)
        sqlite = OutputSectionBuilder().build(bundle, SQLDialect.SQLITE)
        assert postgres.content != sqlite.content
