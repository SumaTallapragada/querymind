"""Join-path resolution over the Metadata Engine's `RelationshipGraph`.

Builds the join paths connecting the tables `SchemaLinker` has resolved
for one query, using only `RelationshipGraph`'s already-implemented
adjacency accessors (`nodes`, `edges_from`) — never an ORM relationship
object, and never `RelationshipGraph.find_related_tables`/
`shortest_path`/`find_join_path`, which are `NotImplementedError` stubs
in the Metadata Engine, explicitly reserved for a later phase. The
breadth-first traversal here is this package's own, built strictly on
top of the graph's public, already-implemented, read-only surface.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from querymind.metadata.relationships import GraphEdge, RelationshipGraph
from querymind.schema_linker.models import ResolvedRelationship


def _to_resolved(edge: GraphEdge) -> ResolvedRelationship:
    return ResolvedRelationship(
        source_table=edge.source_table,
        target_table=edge.target_table,
        relationship_name=edge.relationship_name,
        source_columns=edge.source_columns,
        target_columns=edge.target_columns,
    )


class RelationshipPathResolver:
    """Finds join paths between resolved tables via breadth-first search over `RelationshipGraph`.

    Constructed with one `RelationshipGraph` snapshot (from
    `MetadataRegistry.build_graph()`) and reused for every path lookup
    within a single `SchemaLinker.link()` call.
    """

    def __init__(self, graph: RelationshipGraph) -> None:
        self._graph = graph

    def find_path(self, source_table: str, target_table: str) -> tuple[ResolvedRelationship, ...]:
        """The shortest chain of relationship edges from `source_table` to `target_table`.

        Returns an empty tuple if the two are the same table, either is
        missing from the graph, or no path connects them — BFS over
        unweighted edges, so "shortest" means fewest hops.
        """
        if source_table == target_table:
            return ()
        if source_table not in self._graph.nodes or target_table not in self._graph.nodes:
            return ()

        visited = {source_table}
        queue: deque[tuple[str, tuple[ResolvedRelationship, ...]]] = deque([(source_table, ())])
        while queue:
            current, path_so_far = queue.popleft()
            for edge in self._graph.edges_from(current):
                if edge.target_table == target_table:
                    return (*path_so_far, _to_resolved(edge))
                if edge.target_table not in visited:
                    visited.add(edge.target_table)
                    queue.append((edge.target_table, (*path_so_far, _to_resolved(edge))))
        return ()

    def find_paths_from(
        self, anchor_table: str, other_tables: Iterable[str]
    ) -> tuple[ResolvedRelationship, ...]:
        """The union of shortest paths from `anchor_table` to each of `other_tables`.

        Deduplicated by `(source_table, target_table, relationship_name)`
        and returned in discovery order — the deterministic, "anchor
        outward" approximation of a full Steiner tree this package uses
        to connect every table one query resolved, without pulling in a
        general minimum-Steiner-tree solver for what is, in practice, a
        handful of tables per query.
        """
        seen: set[tuple[str, str, str]] = set()
        edges: list[ResolvedRelationship] = []
        for target in other_tables:
            if target == anchor_table:
                continue
            for edge in self.find_path(anchor_table, target):
                key = (edge.source_table, edge.target_table, edge.relationship_name)
                if key not in seen:
                    seen.add(key)
                    edges.append(edge)
        return tuple(edges)
