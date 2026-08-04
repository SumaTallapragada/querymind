from __future__ import annotations

from pathlib import Path

from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    ResultShape,
)
from querymind.query_library.validator import QueryLibraryValidator, ValidationSeverity


def _example(**overrides: object) -> QueryExample:
    defaults: dict[str, object] = {
        "id": "example_1",
        "title": "Example One",
        "natural_language_question": "How many customers do we have?",
        "normalized_question": "how many customers do we have",
        "query_context": QueryContextSummary(intent="count"),
        "business_concepts": ("revenue",),
        "gold_sql": "SELECT COUNT(*) FROM customers;",
        "sql_explanation": "Counts every customer row.",
        "difficulty": Difficulty.BEGINNER,
        "expected_result_description": "A single number.",
        "expected_result_shape": ResultShape.SCALAR,
    }
    defaults.update(overrides)
    return QueryExample(**defaults)  # type: ignore[arg-type]


def test_well_formed_catalog_has_no_issues() -> None:
    report = QueryLibraryValidator().validate_examples([_example()])
    assert report.is_valid is True
    assert report.issues == ()


def test_duplicate_ids_reported_as_error() -> None:
    report = QueryLibraryValidator().validate_examples(
        [_example(id="a"), _example(id="a", natural_language_question="A different question?")]
    )
    assert report.is_valid is False
    assert any(issue.rule == "unique_ids" for issue in report.errors)


def test_blank_required_field_reported_as_error() -> None:
    report = QueryLibraryValidator().validate_examples([_example(sql_explanation="   ")])
    assert report.is_valid is False
    assert any(issue.rule == "required_fields" for issue in report.errors)


def test_duplicate_questions_reported_as_error() -> None:
    report = QueryLibraryValidator().validate_examples(
        [
            _example(id="a", natural_language_question="How many customers do we have?"),
            _example(id="b", natural_language_question="  HOW many customers DO we have?  "),
        ]
    )
    assert report.is_valid is False
    duplicate_issues = [issue for issue in report.errors if issue.rule == "duplicate_questions"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].example_id == "b"


def test_empty_concepts_reported_as_warning_not_error() -> None:
    report = QueryLibraryValidator().validate_examples([_example(business_concepts=())])
    assert report.is_valid is True  # warnings don't affect validity
    assert any(issue.rule == "empty_concepts" for issue in report.warnings)
    assert not any(issue.rule == "empty_concepts" for issue in report.errors)


def test_missing_sql_reported_as_error() -> None:
    report = QueryLibraryValidator().validate_examples([_example(gold_sql="   ")])
    assert report.is_valid is False
    assert any(issue.rule == "missing_sql" for issue in report.errors)


def test_validate_file_reports_broken_yaml_instead_of_raising(tmp_path: Path) -> None:
    path = tmp_path / "examples.yaml"
    path.write_text("examples: [not: valid: yaml: at: all", encoding="utf-8")
    report = QueryLibraryValidator().validate_file(path)
    assert report.is_valid is False
    assert report.errors[0].rule == "broken_yaml"


def test_validate_file_validates_a_well_formed_file(tmp_path: Path) -> None:
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
    report = QueryLibraryValidator().validate_file(path)
    assert report.is_valid is True


def test_validation_report_errors_and_warnings_partition_issues() -> None:
    report = QueryLibraryValidator().validate_examples(
        [_example(business_concepts=(), gold_sql="")]
    )
    assert all(issue.severity is ValidationSeverity.WARNING for issue in report.warnings)
    assert all(issue.severity is ValidationSeverity.ERROR for issue in report.errors)
    assert set(report.errors) | set(report.warnings) == set(report.issues)
