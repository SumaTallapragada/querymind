from __future__ import annotations

from querymind.metadata.models import RelationshipDirection, RelationshipMetadata
from querymind.metadata.relationships import RelationshipGraph
from querymind.schema_linker.relationships import RelationshipPathResolver


def _edge(source: str, target: str, name: str) -> RelationshipMetadata:
    return RelationshipMetadata(
        name=name,
        source_table=source,
        target_table=target,
        source_columns=(f"{target}_id",),
        target_columns=(f"{target}_id",),
        direction=RelationshipDirection.MANY_TO_ONE,
    )


def _resolver(*edges: RelationshipMetadata, tables: tuple[str, ...]) -> RelationshipPathResolver:
    graph = RelationshipGraph(tables=tables, relationships=edges)
    return RelationshipPathResolver(graph)


def test_direct_edge_is_found() -> None:
    resolver = _resolver(_edge("orders", "customers", "customer"), tables=("orders", "customers"))
    path = resolver.find_path("orders", "customers")
    assert len(path) == 1
    assert path[0].source_table == "orders"
    assert path[0].target_table == "customers"
    assert path[0].relationship_name == "customer"


def test_same_table_returns_empty_path() -> None:
    resolver = _resolver(tables=("orders",))
    assert resolver.find_path("orders", "orders") == ()


def test_unreachable_table_returns_empty_path() -> None:
    resolver = _resolver(tables=("orders", "customers"))
    assert resolver.find_path("orders", "customers") == ()


def test_unknown_table_returns_empty_path() -> None:
    resolver = _resolver(tables=("orders",))
    assert resolver.find_path("orders", "does_not_exist") == ()


def test_multi_hop_path_is_found_via_bfs() -> None:
    resolver = _resolver(
        _edge("order_items", "orders", "order"),
        _edge("orders", "customers", "customer"),
        tables=("order_items", "orders", "customers"),
    )
    path = resolver.find_path("order_items", "customers")
    assert [edge.source_table for edge in path] == ["order_items", "orders"]
    assert [edge.target_table for edge in path] == ["orders", "customers"]


def test_bfs_finds_the_shortest_path_not_a_longer_alternative() -> None:
    resolver = _resolver(
        _edge("a", "b", "ab"),
        _edge("b", "c", "bc"),
        _edge("a", "c", "ac"),  # direct shortcut, should win over a->b->c
        tables=("a", "b", "c"),
    )
    path = resolver.find_path("a", "c")
    assert len(path) == 1
    assert path[0].relationship_name == "ac"


def test_find_paths_from_unions_and_deduplicates_multiple_targets() -> None:
    resolver = _resolver(
        _edge("order_items", "orders", "order"),
        _edge("orders", "customers", "customer"),
        _edge("order_items", "products", "product"),
        tables=("order_items", "orders", "customers", "products"),
    )
    paths = resolver.find_paths_from("order_items", ["customers", "products", "order_items"])
    relationship_names = {edge.relationship_name for edge in paths}
    assert relationship_names == {"order", "customer", "product"}
    # The order->customers hop must appear exactly once even though it's
    # reachable while resolving the path to "customers".
    assert len(paths) == 3
