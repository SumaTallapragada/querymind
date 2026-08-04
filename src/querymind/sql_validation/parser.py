"""Wraps sqlglot: parsing plus AST-traversal helpers every validator reuses.

The single place `sqlglot` itself is imported directly by this package —
every validator operates on the `ParsedSQL`/reference types defined here,
never on `sqlglot` internals directly, and never builds its own SQL
parser or regex-based SQL inspection. Sharing these extraction helpers
(rather than each validator re-walking the AST its own way) is what lets
"no validator should know about another validator" hold while still
avoiding tables/columns/joins/functions each being extracted ten
different times, ten different ways.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from querymind.sql_validation.exceptions import SQLSyntaxError


@dataclass(frozen=True, slots=True)
class ParsedSQL:
    """The sqlglot AST for one SQL string, plus the dialect it was parsed under."""

    ast: exp.Expression
    dialect: str
    raw_sql: str


class SQLParser:
    """Parses SQL text into a sqlglot AST. The only place `sqlglot.parse_one` is called."""

    def parse(self, sql: str, *, dialect: str = "postgres") -> ParsedSQL:
        """Parse `sql`. Raises `SQLSyntaxError` if sqlglot cannot parse it."""
        try:
            ast = sqlglot.parse_one(sql, dialect=dialect)
        except ParseError as exc:
            raise SQLSyntaxError(str(exc)) from exc
        return ParsedSQL(ast=ast, dialect=dialect, raw_sql=sql)


@dataclass(frozen=True, slots=True)
class TableReference:
    """One base-table (or CTE/derived-table) reference found in a query."""

    name: str
    alias: str | None
    node: exp.Table


@dataclass(frozen=True, slots=True)
class ColumnReference:
    """One column reference found in a query."""

    name: str
    qualifier: str | None
    node: exp.Column


@dataclass(frozen=True, slots=True)
class JoinReference:
    """One JOIN clause, with its two sides resolved to real table names where determinable."""

    join_type: str
    left_table: str | None
    right_table: str | None
    on_columns: tuple[str, ...]
    node: exp.Join


@dataclass(frozen=True, slots=True)
class FunctionReference:
    """One function call, with its name rendered as it would appear in the target dialect's SQL."""

    name: str
    node: exp.Func


def cte_names(ast: exp.Expression) -> frozenset[str]:
    """Every name introduced by a `WITH ... AS (...)` clause in this query."""
    return frozenset(cte.alias for cte in ast.find_all(exp.CTE) if cte.alias)


def derived_table_aliases(ast: exp.Expression) -> frozenset[str]:
    """Every alias given to a subquery used as a table (`FROM (SELECT ...) AS x`)."""
    return frozenset(subquery.alias for subquery in ast.find_all(exp.Subquery) if subquery.alias)


def local_scope_names(ast: exp.Expression) -> frozenset[str]:
    """Names that exist only within this one query: CTEs and derived-table aliases.

    Never checked against the Metadata Engine — sqlglot alone can't infer
    a CTE's or derived table's result shape without deeper type
    inference, which is out of scope for this package (it operates on
    the AST sqlglot produces, not a full SQL type checker).
    """
    return cte_names(ast) | derived_table_aliases(ast)


def extract_tables(ast: exp.Expression) -> tuple[TableReference, ...]:
    """Every `exp.Table` node in the query — base tables, and CTE names used as a FROM/JOIN source."""
    return tuple(
        TableReference(name=table.name, alias=table.alias or None, node=table)
        for table in ast.find_all(exp.Table)
    )


def extract_columns(ast: exp.Expression) -> tuple[ColumnReference, ...]:
    """Every `exp.Column` node in the query, qualified or not."""
    return tuple(
        ColumnReference(name=column.name, qualifier=column.table or None, node=column)
        for column in ast.find_all(exp.Column)
    )


def build_alias_map(ast: exp.Expression) -> dict[str, str]:
    """Every qualifier a column reference could legally use -> the name it refers to.

    Maps a table's alias (or its own name, if unaliased) to its real
    name, plus every derived-table alias to itself (there is no "real"
    underlying name for a derived table to resolve to).
    """
    mapping: dict[str, str] = {}
    for ref in extract_tables(ast):
        mapping[ref.alias or ref.name] = ref.name
    for alias in derived_table_aliases(ast):
        mapping[alias] = alias
    return mapping


def extract_joins(ast: exp.Expression) -> tuple[JoinReference, ...]:
    """Every `exp.Join` clause, with its left/right tables resolved via the ON condition's qualifiers.

    The "right" table is the join's own target (`JOIN <right> ON ...`).
    The "left" table is inferred as whichever *other* qualifier appears
    in the ON condition — a heuristic, not a full scope analysis, but
    correct for the ordinary case of one ON condition connecting exactly
    two tables. A CROSS JOIN (no ON condition) always resolves
    `left_table` to `None`, since there is nothing to infer it from.
    """
    alias_map = build_alias_map(ast)
    joins: list[JoinReference] = []
    for join_node in ast.find_all(exp.Join):
        right_table_node = join_node.this
        # `.name` on an `exp.Table` node is already its real table name -- no alias_map
        # lookup needed (and a lookup by real name would wrongly miss any table that
        # *does* have an alias, since build_alias_map only keys aliased tables by their
        # alias, not also by their real name).
        right_resolved = right_table_node.name if isinstance(right_table_node, exp.Table) else None
        right_alias = (
            (right_table_node.alias or right_table_node.name)
            if isinstance(right_table_node, exp.Table)
            else None
        )

        on_condition = join_node.args.get("on")
        on_columns = (
            tuple(c.name for c in on_condition.find_all(exp.Column)) if on_condition else ()
        )
        on_qualifiers = (
            {c.table for c in on_condition.find_all(exp.Column) if c.table}
            if on_condition
            else set()
        )
        left_qualifiers = on_qualifiers - {right_alias} if right_alias else on_qualifiers
        left_resolved = alias_map.get(next(iter(left_qualifiers))) if left_qualifiers else None

        join_type = (join_node.kind or join_node.side or "INNER").upper()
        joins.append(
            JoinReference(
                join_type=join_type,
                left_table=left_resolved,
                right_table=right_resolved,
                on_columns=on_columns,
                node=join_node,
            )
        )
    return tuple(joins)


def extract_functions(
    ast: exp.Expression, *, dialect: str = "postgres"
) -> tuple[FunctionReference, ...]:
    """Every function call, named as it would render in `dialect`'s SQL text.

    Excludes the internal `exp.If` nodes sqlglot uses to represent a
    `CASE`'s own `WHEN`/`THEN` branches — those are not independent
    function calls the SQL author wrote, they're part of the one `CASE`
    expression already yielded separately.
    """
    results: list[FunctionReference] = []
    for func_node in ast.find_all(exp.Func):
        if isinstance(func_node, exp.If) and isinstance(func_node.parent, exp.Case):
            continue
        if isinstance(func_node, exp.Case):
            name = "CASE"
        else:
            rendered = func_node.sql(dialect=dialect)
            name = rendered.split("(", 1)[0].strip().upper()
        results.append(FunctionReference(name=name, node=func_node))
    return tuple(results)
