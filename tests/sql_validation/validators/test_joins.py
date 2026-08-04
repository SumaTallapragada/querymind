"""Tests for `querymind.sql_validation.validators.joins.JoinValidator`."""

from __future__ import annotations

from querymind.metadata.relationships import RelationshipGraph
from querymind.sql_validation.models import ValidationSeverity
from querymind.sql_validation.validators.joins import JoinValidator
from tests.sql_validation.conftest import parse


class TestKnownRelationship:
    def test_a_join_following_a_real_relationship_produces_no_issues(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert issues == ()

    def test_the_relationship_can_be_declared_in_either_direction(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        # orders -> customers is the declared edge; joining from customers still works
        # since JoinValidator checks both directions.
        sql = "SELECT * FROM orders o JOIN customers c ON c.customer_id = o.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert issues == ()


class TestHallucinatedJoin:
    def test_a_join_between_unrelated_tables_is_flagged(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        sql = "SELECT * FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert len(issues) == 1
        assert issues[0].code == "unknown_join_relationship"

    def test_the_related_object_names_both_tables(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        sql = "SELECT * FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        related_object = issues[0].related_object
        assert related_object is not None
        assert "customers" in related_object
        assert "warehouses" in related_object


class TestMismatchedJoinColumns:
    def test_a_relationship_exists_but_the_on_clause_uses_unrelated_columns(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        # A real relationship connects orders/customers via customer_id, but this ON
        # clause compares columns that share no name with that relationship at all --
        # a warning, not an error, since this heuristic only checks column names, not
        # full column-level semantic matching.
        sql = "SELECT * FROM customers c JOIN orders o ON o.total_amount = c.first_name;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert len(issues) == 1
        assert issues[0].code == "join_columns_do_not_match_relationship"
        assert issues[0].severity is ValidationSeverity.WARNING

    def test_an_on_clause_naming_the_relationships_own_key_column_is_not_flagged(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        # Even though order_id has nothing to do with customer_id, the ON clause still
        # names "customer_id" on one side -- the heuristic only checks column-name
        # overlap with the known relationship, not that both sides make sense together.
        sql = "SELECT * FROM customers c JOIN orders o ON o.order_id = c.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert issues == ()


class TestCrossJoinIsSkipped:
    def test_a_cross_join_is_never_flagged(self, relationship_graph: RelationshipGraph) -> None:
        sql = "SELECT * FROM customers c CROSS JOIN warehouses w;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert issues == ()


class TestUnknownTablesAreSkipped:
    def test_a_join_involving_an_unknown_table_is_not_flagged_here(
        self, relationship_graph: RelationshipGraph
    ) -> None:
        # SchemaValidator/TableValidator own "unknown table" -- JoinValidator must not
        # pile on a confusing second error about a table that doesn't exist at all.
        sql = "SELECT * FROM customers c JOIN nonexistent_table n ON n.id = c.customer_id;"
        issues = JoinValidator(relationship_graph).validate(parse(sql))
        assert issues == ()
