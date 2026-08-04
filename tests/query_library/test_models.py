from __future__ import annotations

import pytest

from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    ResultShape,
    SQLDialect,
)


def _example(**overrides: object) -> QueryExample:
    defaults: dict[str, object] = {
        "id": "customer_count",
        "title": "Total Customer Count",
        "natural_language_question": "How many customers do we have?",
        "normalized_question": "how many customers do we have",
        "query_context": QueryContextSummary(intent="count"),
        "gold_sql": "SELECT COUNT(*) FROM customers;",
        "sql_explanation": "Counts every customer row.",
        "difficulty": Difficulty.BEGINNER,
        "expected_result_description": "A single number.",
        "expected_result_shape": ResultShape.SCALAR,
    }
    defaults.update(overrides)
    return QueryExample(**defaults)  # type: ignore[arg-type]


def test_minimal_example_has_sensible_defaults() -> None:
    example = _example()
    assert example.business_concepts == ()
    assert example.linked_schema_objects == ()
    assert example.tags == ()
    assert example.common_variations == ()
    assert example.notes is None
    assert example.dialect is SQLDialect.POSTGRESQL


def test_model_is_frozen() -> None:
    example = _example()
    with pytest.raises(Exception, match="frozen|immutable"):
        example.title = "Something Else"  # type: ignore[misc]


def test_query_context_summary_defaults() -> None:
    summary = QueryContextSummary(intent="top_n")
    assert summary.primary_entity is None
    assert summary.metrics == ()
    assert summary.dimensions == ()
    assert summary.aggregation is None


def test_rejects_unknown_fields() -> None:
    with pytest.raises(Exception, match="extra|Extra"):
        _example(unexpected_field="oops")
