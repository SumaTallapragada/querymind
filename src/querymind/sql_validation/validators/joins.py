"""Checks every JOIN follows a real, known relationship — no hallucinated joins.

Sourced from `querymind.metadata.relationships.RelationshipGraph`, built
by the existing Metadata Engine. Only uses the graph's already-implemented
adjacency accessors (`edges_from`) — `find_related_tables`/`shortest_path`/
`find_join_path` are documented `NotImplementedError` stubs in that class
and are never called here.
"""

from __future__ import annotations

from querymind.metadata.relationships import RelationshipGraph
from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL, extract_joins

#: A CROSS JOIN is a deliberate cartesian product with no ON condition —
#: it has no relationship to check against and is skipped entirely.
_SKIPPED_JOIN_TYPES = frozenset({"CROSS"})


class JoinValidator:
    """Validates that every JOIN connects two tables with a known relationship between them."""

    name = "join"

    def __init__(self, relationship_graph: RelationshipGraph) -> None:
        self._relationship_graph = relationship_graph

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []

        for join in extract_joins(parsed.ast):
            if join.join_type in _SKIPPED_JOIN_TYPES:
                continue
            if join.left_table is None or join.right_table is None:
                continue  # a derived-table/CTE join, or an ON condition we couldn't resolve
            if join.left_table not in self._relationship_graph.nodes:
                continue  # unknown table -- SchemaValidator/TableValidator already report this
            if join.right_table not in self._relationship_graph.nodes:
                continue

            if not self._has_relationship(join.left_table, join.right_table):
                issues.append(
                    ValidationIssue(
                        code="unknown_join_relationship",
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"No known relationship connects {join.left_table!r} and "
                            f"{join.right_table!r} — this JOIN does not follow the schema."
                        ),
                        related_object=f"{join.left_table}-{join.right_table}",
                    )
                )
                continue

            if join.on_columns and not self._on_condition_matches_a_relationship(
                join.left_table, join.right_table, join.on_columns
            ):
                issues.append(
                    ValidationIssue(
                        code="join_columns_do_not_match_relationship",
                        severity=ValidationSeverity.WARNING,
                        message=(
                            f"A relationship exists between {join.left_table!r} and "
                            f"{join.right_table!r}, but this JOIN's ON condition doesn't match "
                            "its declared columns."
                        ),
                        related_object=f"{join.left_table}-{join.right_table}",
                    )
                )

        return tuple(issues)

    def _has_relationship(self, left_table: str, right_table: str) -> bool:
        forward = any(
            edge.target_table == right_table
            for edge in self._relationship_graph.edges_from(left_table)
        )
        backward = any(
            edge.target_table == left_table
            for edge in self._relationship_graph.edges_from(right_table)
        )
        return forward or backward

    def _on_condition_matches_a_relationship(
        self, left_table: str, right_table: str, on_columns: tuple[str, ...]
    ) -> bool:
        on_column_set = set(on_columns)
        for edge in (
            *self._relationship_graph.edges_from(left_table),
            *self._relationship_graph.edges_from(right_table),
        ):
            if edge.target_table not in (left_table, right_table):
                continue
            edge_columns = set(edge.source_columns) | set(edge.target_columns)
            if edge_columns & on_column_set:
                return True
        return False
