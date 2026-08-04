from __future__ import annotations

from pathlib import Path

import pytest

from querymind.query_library.catalog import build_library, load_library
from querymind.query_library.exceptions import DuplicateExampleError
from querymind.query_library.models import QueryContextSummary, QueryExample


def _example(example_id: str, title: str) -> QueryExample:
    from querymind.query_library.models import Difficulty, ResultShape

    return QueryExample(
        id=example_id,
        title=title,
        natural_language_question="x?",
        normalized_question="x",
        query_context=QueryContextSummary(intent="count"),
        gold_sql="SELECT 1;",
        sql_explanation="x",
        difficulty=Difficulty.BEGINNER,
        expected_result_description="x",
        expected_result_shape=ResultShape.SCALAR,
    )


def test_build_library_assembles_examples_and_sets_loaded_at() -> None:
    library = build_library([_example("a", "A"), _example("b", "B")])
    assert [e.id for e in library.examples] == ["a", "b"]
    assert library.loaded_at is not None


def test_build_library_rejects_duplicate_ids() -> None:
    with pytest.raises(DuplicateExampleError, match="a"):
        build_library([_example("a", "A"), _example("a", "Also A")])


def test_load_library_reads_and_assembles_a_real_file(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text(
        """
examples:
  - id: customer_count
    title: Total Customer Count
    natural_language_question: "How many customers?"
    normalized_question: "how many customers"
    query_context:
      intent: count
    gold_sql: "SELECT COUNT(*) FROM customers;"
    sql_explanation: "x"
    difficulty: beginner
    expected_result_description: "x"
    expected_result_shape: scalar
""",
        encoding="utf-8",
    )
    library = load_library(path)
    assert len(library.examples) == 1
    assert library.examples[0].id == "customer_count"


def test_load_library_default_path_loads_the_shipped_catalog() -> None:
    library = load_library()
    assert len(library.examples) > 0
