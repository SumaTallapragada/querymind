"""Content-quality validation for the query example library.

Distinct from `loader.py` (which already guarantees every successfully
loaded `QueryExample` is *structurally* valid — required fields present,
`difficulty`/`dialect` are real enum members, ...): this module runs
*cross-entry* and *content-quality* checks that Pydantic's per-object
schema validation can't express — duplicate ids across entries, two
examples asking the same question, a `gold_sql` that's just whitespace.
Every problem found is reported as data (`ValidationIssue`) in one
`ValidationReport`, never raised, so a caller checking a whole catalog
file gets every problem at once instead of stopping at the first one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from querymind.query_library.exceptions import LibraryLoadError
from querymind.query_library.loader import load_examples_file
from querymind.query_library.models import Difficulty, QueryExample, SQLDialect


class ValidationSeverity(str, Enum):
    """How serious a `ValidationIssue` is."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation problem found in the catalog."""

    rule: str
    severity: ValidationSeverity
    message: str
    example_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Every problem `QueryLibraryValidator` found, in check order."""

    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the catalog has zero `ERROR`-severity issues. `WARNING`s don't affect this."""
        return not any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.WARNING)


class QueryLibraryValidator:
    """Runs deterministic content-quality checks against a query example catalog.

    Two entry points: `validate_examples` (pure, operates on
    already-loaded `QueryExample` objects) and `validate_file` (also
    loads a YAML file, so a load failure becomes a `"broken_yaml"` issue
    in the report instead of a raised exception).
    """

    def validate_file(self, path: Path) -> ValidationReport:
        """Validate the examples YAML file at `path`, including the load step itself."""
        try:
            examples = load_examples_file(path)
        except LibraryLoadError as exc:
            return ValidationReport(
                issues=(
                    ValidationIssue(
                        rule="broken_yaml", severity=ValidationSeverity.ERROR, message=str(exc)
                    ),
                )
            )
        return self.validate_examples(examples)

    def validate_examples(self, examples: Sequence[QueryExample]) -> ValidationReport:
        """Validate an already-loaded set of `QueryExample`s."""
        issues: list[ValidationIssue] = []
        issues.extend(self._check_unique_ids(examples))
        issues.extend(self._check_required_fields(examples))
        issues.extend(self._check_valid_dialect(examples))
        issues.extend(self._check_valid_difficulty(examples))
        issues.extend(self._check_duplicate_questions(examples))
        issues.extend(self._check_empty_concepts(examples))
        issues.extend(self._check_missing_sql(examples))
        return ValidationReport(issues=tuple(issues))

    @staticmethod
    def _check_unique_ids(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        seen: set[str] = set()
        issues: list[ValidationIssue] = []
        for example in examples:
            if example.id in seen:
                issues.append(
                    ValidationIssue(
                        rule="unique_ids",
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate example id {example.id!r}.",
                        example_id=example.id,
                    )
                )
            seen.add(example.id)
        return issues

    @staticmethod
    def _check_required_fields(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        """Flag fields that are technically present (Pydantic requires them) but blank/whitespace-only."""
        required_text_fields = (
            "title",
            "natural_language_question",
            "sql_explanation",
            "expected_result_description",
        )
        issues: list[ValidationIssue] = []
        for example in examples:
            for field_name in required_text_fields:
                if not getattr(example, field_name).strip():
                    issues.append(
                        ValidationIssue(
                            rule="required_fields",
                            severity=ValidationSeverity.ERROR,
                            message=f"Field {field_name!r} is blank.",
                            example_id=example.id,
                        )
                    )
        return issues

    @staticmethod
    def _check_valid_dialect(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        """Defensive/explicit: `SQLDialect` is already enum-enforced at load time, so this can
        only ever find a problem if a `QueryExample` was constructed outside the normal loader."""
        issues: list[ValidationIssue] = []
        for example in examples:
            if example.dialect not in SQLDialect:
                issues.append(
                    ValidationIssue(
                        rule="valid_dialect",
                        severity=ValidationSeverity.ERROR,
                        message=f"{example.dialect!r} is not a recognized SQL dialect.",
                        example_id=example.id,
                    )
                )
        return issues

    @staticmethod
    def _check_valid_difficulty(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        """Defensive/explicit: see `_check_valid_dialect` — `Difficulty` is enum-enforced at load time."""
        issues: list[ValidationIssue] = []
        for example in examples:
            if example.difficulty not in Difficulty:
                issues.append(
                    ValidationIssue(
                        rule="valid_difficulty",
                        severity=ValidationSeverity.ERROR,
                        message=f"{example.difficulty!r} is not a recognized difficulty.",
                        example_id=example.id,
                    )
                )
        return issues

    @staticmethod
    def _check_duplicate_questions(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        """Two examples asking the same question (normalized) is almost always an authoring mistake —
        genuine alternate phrasings belong in one example's `common_variations`, not a second entry."""
        seen: dict[str, str] = {}
        issues: list[ValidationIssue] = []
        for example in examples:
            key = " ".join(example.natural_language_question.strip().lower().split())
            if key in seen:
                issues.append(
                    ValidationIssue(
                        rule="duplicate_questions",
                        severity=ValidationSeverity.ERROR,
                        message=f"Same question as {seen[key]!r}: {example.natural_language_question!r}",
                        example_id=example.id,
                    )
                )
            else:
                seen[key] = example.id
        return issues

    @staticmethod
    def _check_empty_concepts(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for example in examples:
            if not example.business_concepts:
                issues.append(
                    ValidationIssue(
                        rule="empty_concepts",
                        severity=ValidationSeverity.WARNING,
                        message="No business_concepts declared; this example won't surface in "
                        "concept-based search.",
                        example_id=example.id,
                    )
                )
        return issues

    @staticmethod
    def _check_missing_sql(examples: Sequence[QueryExample]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for example in examples:
            if not example.gold_sql.strip():
                issues.append(
                    ValidationIssue(
                        rule="missing_sql",
                        severity=ValidationSeverity.ERROR,
                        message="gold_sql is blank.",
                        example_id=example.id,
                    )
                )
        return issues
