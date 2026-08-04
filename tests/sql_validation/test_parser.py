"""Tests for `querymind.sql_validation.parser` — sqlglot parsing and AST traversal helpers."""

from __future__ import annotations

import pytest
from sqlglot import exp

from querymind.sql_validation.exceptions import SQLSyntaxError
from querymind.sql_validation.parser import (
    SQLParser,
    build_alias_map,
    cte_names,
    derived_table_aliases,
    extract_columns,
    extract_functions,
    extract_joins,
    extract_tables,
    local_scope_names,
)


class TestSQLParser:
    def test_parses_valid_sql_into_a_select_ast(self) -> None:
        parsed = SQLParser().parse("SELECT 1;")
        assert isinstance(parsed.ast, exp.Select)
        assert parsed.dialect == "postgres"
        assert parsed.raw_sql == "SELECT 1;"

    def test_uses_the_requested_dialect(self) -> None:
        parsed = SQLParser().parse("SELECT 1;", dialect="mysql")
        assert parsed.dialect == "mysql"

    def test_raises_sql_syntax_error_on_malformed_sql(self) -> None:
        with pytest.raises(SQLSyntaxError):
            SQLParser().parse("SELECT FROM WHERE;")

    def test_syntax_error_message_is_informative(self) -> None:
        with pytest.raises(SQLSyntaxError, match="table name"):
            SQLParser().parse("SELECT FROM WHERE;")


class TestExtractTables:
    def test_finds_every_table_with_its_alias(self) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        refs = extract_tables(SQLParser().parse(sql).ast)
        assert {(ref.name, ref.alias) for ref in refs} == {("customers", "c"), ("orders", "o")}

    def test_unaliased_table_has_a_none_alias(self) -> None:
        refs = extract_tables(SQLParser().parse("SELECT * FROM customers;").ast)
        assert refs[0].alias is None


class TestExtractColumns:
    def test_finds_qualified_and_unqualified_columns(self) -> None:
        sql = "SELECT c.customer_id, first_name FROM customers c;"
        columns = extract_columns(SQLParser().parse(sql).ast)
        assert ("customer_id", "c") in {(c.name, c.qualifier) for c in columns}
        assert ("first_name", None) in {(c.name, c.qualifier) for c in columns}


class TestBuildAliasMap:
    def test_maps_alias_to_real_table_name(self) -> None:
        sql = "SELECT * FROM customers c;"
        mapping = build_alias_map(SQLParser().parse(sql).ast)
        assert mapping == {"c": "customers"}

    def test_unaliased_table_is_keyed_by_its_own_name(self) -> None:
        mapping = build_alias_map(SQLParser().parse("SELECT * FROM customers;").ast)
        assert mapping == {"customers": "customers"}

    def test_derived_table_alias_maps_to_itself(self) -> None:
        sql = "SELECT sub.x FROM (SELECT id AS x FROM customers) AS sub;"
        mapping = build_alias_map(SQLParser().parse(sql).ast)
        assert mapping["sub"] == "sub"


class TestExtractJoins:
    def test_resolves_both_sides_of_a_simple_join(self) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert len(joins) == 1
        assert joins[0].left_table == "customers"
        assert joins[0].right_table == "orders"
        assert set(joins[0].on_columns) == {"customer_id"}

    def test_resolves_the_right_table_even_when_it_has_no_alias(self) -> None:
        # Regression case: the right table's real name must never be looked up
        # through the alias map (whose keys are aliases, not real names).
        sql = "SELECT * FROM customers c JOIN orders ON orders.customer_id = c.customer_id;"
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert joins[0].right_table == "orders"

    def test_join_type_defaults_to_inner(self) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert joins[0].join_type == "INNER"

    def test_left_join_type_is_detected(self) -> None:
        sql = "SELECT * FROM customers c LEFT JOIN orders o ON o.customer_id = c.customer_id;"
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert joins[0].join_type == "LEFT"

    def test_cross_join_has_no_resolvable_left_table(self) -> None:
        sql = "SELECT * FROM customers c CROSS JOIN warehouses w;"
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert joins[0].join_type == "CROSS"
        assert joins[0].left_table is None

    def test_a_chain_of_joins_resolves_each_pair_correctly(self) -> None:
        sql = (
            "SELECT * FROM customers c "
            "JOIN orders o ON o.customer_id = c.customer_id "
            "JOIN order_items i ON i.order_id = o.order_id;"
        )
        joins = extract_joins(SQLParser().parse(sql).ast)
        assert len(joins) == 2
        assert (joins[0].left_table, joins[0].right_table) == ("customers", "orders")
        assert (joins[1].left_table, joins[1].right_table) == ("orders", "order_items")


class TestExtractFunctions:
    def test_finds_a_simple_function_call(self) -> None:
        functions = extract_functions(SQLParser().parse("SELECT SUM(x) FROM t;").ast)
        assert [f.name for f in functions] == ["SUM"]

    def test_case_is_named_case_not_its_internal_if_branches(self) -> None:
        sql = "SELECT CASE WHEN a THEN 1 ELSE 0 END FROM t;"
        functions = extract_functions(SQLParser().parse(sql).ast)
        assert [f.name for f in functions] == ["CASE"]

    def test_date_trunc_is_named_for_the_target_dialect(self) -> None:
        sql = "SELECT DATE_TRUNC('month', d) FROM t;"
        functions = extract_functions(SQLParser().parse(sql).ast, dialect="postgres")
        assert [f.name for f in functions] == ["DATE_TRUNC"]

    def test_finds_nested_function_calls(self) -> None:
        functions = extract_functions(SQLParser().parse("SELECT ROUND(SUM(x), 2) FROM t;").ast)
        assert {f.name for f in functions} == {"ROUND", "SUM"}


class TestLocalScopeNames:
    def test_a_cte_name_is_a_local_scope_name(self) -> None:
        sql = "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent;"
        assert cte_names(SQLParser().parse(sql).ast) == frozenset({"recent"})
        assert "recent" in local_scope_names(SQLParser().parse(sql).ast)

    def test_a_derived_table_alias_is_a_local_scope_name(self) -> None:
        sql = "SELECT sub.x FROM (SELECT id AS x FROM customers) AS sub;"
        assert derived_table_aliases(SQLParser().parse(sql).ast) == frozenset({"sub"})
        assert "sub" in local_scope_names(SQLParser().parse(sql).ast)

    def test_a_real_table_is_not_a_local_scope_name(self) -> None:
        assert local_scope_names(SQLParser().parse("SELECT * FROM customers;").ast) == frozenset()
