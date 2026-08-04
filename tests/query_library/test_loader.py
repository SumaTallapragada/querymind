from __future__ import annotations

from pathlib import Path

import pytest

from querymind.query_library.exceptions import LibraryLoadError
from querymind.query_library.loader import load_examples_file

_VALID_YAML = """
examples:
  - id: customer_count
    title: Total Customer Count
    natural_language_question: "How many customers do we have?"
    normalized_question: "how many customers do we have"
    query_context:
      intent: count
      primary_entity: customer
      aggregation: count
    gold_sql: "SELECT COUNT(*) FROM customers;"
    sql_explanation: "Counts every customer row."
    difficulty: beginner
    expected_result_description: "A single number."
    expected_result_shape: scalar
  - id: order_count
    title: Total Order Count
    natural_language_question: "How many orders do we have?"
    normalized_question: "how many orders do we have"
    query_context:
      intent: count
      primary_entity: order
    gold_sql: "SELECT COUNT(*) FROM orders;"
    sql_explanation: "Counts every order row."
    difficulty: beginner
    expected_result_description: "A single number."
    expected_result_shape: scalar
"""


def test_loads_valid_yaml_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text(_VALID_YAML, encoding="utf-8")
    examples = load_examples_file(path)
    assert [e.id for e in examples] == ["customer_count", "order_count"]
    assert examples[0].title == "Total Customer Count"
    assert examples[0].query_context.intent == "count"


def test_missing_file_raises_library_load_error(tmp_path: Path) -> None:
    with pytest.raises(LibraryLoadError, match="could not read file"):
        load_examples_file(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_library_load_error(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text("examples: [this is not: valid: yaml: at all", encoding="utf-8")
    with pytest.raises(LibraryLoadError, match="invalid YAML"):
        load_examples_file(path)


def test_missing_examples_key_raises_library_load_error(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text("not_examples: []", encoding="utf-8")
    with pytest.raises(LibraryLoadError, match="missing top-level 'examples' key"):
        load_examples_file(path)


def test_schema_validation_failure_raises_library_load_error(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text(
        """
examples:
  - id: bad_example
    title: Bad Example
    natural_language_question: "x"
    normalized_question: "x"
    query_context:
      intent: count
    gold_sql: "SELECT 1;"
    sql_explanation: "x"
    difficulty: not_a_real_difficulty
    expected_result_description: "x"
    expected_result_shape: scalar
""",
        encoding="utf-8",
    )
    with pytest.raises(LibraryLoadError, match="schema validation failed"):
        load_examples_file(path)


def test_default_library_path_exists() -> None:
    from querymind.query_library.loader import DEFAULT_LIBRARY_PATH

    assert DEFAULT_LIBRARY_PATH.exists()
