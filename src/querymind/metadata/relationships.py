"""The table-relationship graph.

`RelationshipGraph` builds an adjacency-list representation of every
table and the relationships between them. Construction, and the direct,
O(1)/O(degree) structural accessors it enables (`nodes`, `edges_from`,
`neighbors`), are implemented now. Genuine graph *algorithms* —
multi-hop reachability, shortest path, and join-path resolution — are
deliberately left as documented stubs: the data structure they will
traverse is what this phase builds, not the traversal logic itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from querymind.metadata.models import RelationshipMetadata


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One relationship edge from `source_table` to `target_table`."""

    source_table: str
    target_table: str
    relationship_name: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]

    @classmethod
    def from_relationship(cls, relationship: RelationshipMetadata) -> GraphEdge:
        return cls(
            source_table=relationship.source_table,
            target_table=relationship.target_table,
            relationship_name=relationship.name,
            source_columns=relationship.source_columns,
            target_columns=relationship.target_columns,
        )


class RelationshipGraph:
    """An adjacency-list graph over tables, built from `RelationshipMetadata`.

    Construct via `MetadataRegistry.build_graph()` — or directly, for
    testing, from any `tables`/`relationships` pair without a live
    registry. Every relationship becomes one directed edge from its
    `source_table` to its `target_table`; the reverse ORM relationship
    (e.g. both `Order.customer` and `Customer.orders` exist) naturally
    produces the reverse edge too, so the graph is effectively
    bidirectional between any two related tables.
    """

    def __init__(
        self, tables: Iterable[str], relationships: Iterable[RelationshipMetadata]
    ) -> None:
        self._nodes: frozenset[str] = frozenset(tables)
        self._adjacency: dict[str, tuple[GraphEdge, ...]] = self._build_adjacency(relationships)

    @staticmethod
    def _build_adjacency(
        relationships: Iterable[RelationshipMetadata],
    ) -> dict[str, tuple[GraphEdge, ...]]:
        grouped: dict[str, list[GraphEdge]] = {}
        for relationship in relationships:
            grouped.setdefault(relationship.source_table, []).append(
                GraphEdge.from_relationship(relationship)
            )
        return {table: tuple(edges) for table, edges in grouped.items()}

    @property
    def nodes(self) -> frozenset[str]:
        """Every table in the graph, whether or not it has any relationships."""
        return self._nodes

    def edges_from(self, table: str) -> tuple[GraphEdge, ...]:
        """The outgoing relationship edges declared on `table`.

        A direct lookup on the adjacency structure built at construction
        time — not a traversal.
        """
        return self._adjacency.get(table, ())

    def neighbors(self, table: str) -> tuple[str, ...]:
        """Tables directly reachable from `table` via exactly one relationship hop.

        Still a direct adjacency lookup, not a graph algorithm — see
        `find_related_tables` for the transitive (multi-hop) version.
        """
        return tuple(edge.target_table for edge in self.edges_from(table))

    def find_related_tables(self, table: str, *, max_depth: int | None = None) -> tuple[str, ...]:
        """Find every table transitively reachable from `table`.

        Requires a graph traversal (BFS/DFS) over `edges_from`/`neighbors`
        up to `max_depth` hops (or unbounded if `None`) — not implemented
        yet. This phase only builds the adjacency structure the traversal
        will run on.
        """
        raise NotImplementedError("Graph traversal is implemented in a later phase.")

    def shortest_path(self, source_table: str, target_table: str) -> tuple[str, ...]:
        """Find the shortest sequence of tables connecting `source_table` to `target_table`.

        Requires a shortest-path algorithm (e.g. BFS, since edges are
        unweighted) — not implemented yet.
        """
        raise NotImplementedError("Shortest-path search is implemented in a later phase.")

    def find_join_path(self, source_table: str, target_table: str) -> tuple[GraphEdge, ...]:
        """Find the chain of relationship edges needed to SQL-join `source_table` to `target_table`.

        Distinct from `shortest_path`: this returns the edges themselves
        (relationship name and join columns), which is what a future SQL
        generator would need to actually write the `JOIN` clauses — not
        implemented yet.
        """
        raise NotImplementedError("Join-path resolution is implemented in a later phase.")
