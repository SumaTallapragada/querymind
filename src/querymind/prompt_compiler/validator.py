"""Content-quality validation for a compiled prompt's sections.

Distinct from `models.py`'s Pydantic schema validation (which already
guarantees every field is present and correctly typed): this module runs
*cross-section* checks Pydantic can't express — a required section
missing from the set entirely, duplicate examples across the retrieved
example section, the combined token budget being exceeded. Every problem
found is reported as data (`PromptValidationIssue`) in one
`PromptValidationReport`, never raised — mirrors
`querymind.query_library.validator.QueryLibraryValidator` exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from querymind.prompt_compiler.budget import DEFAULT_MAX_TOKENS
from querymind.prompt_compiler.models import ExampleSection, PromptSection, SectionName


class ValidationSeverity(str, Enum):
    """How serious a `PromptValidationIssue` is."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class PromptValidationIssue:
    """One validation problem found in a compiled prompt's sections."""

    rule: str
    severity: ValidationSeverity
    message: str
    section: SectionName | None = None


@dataclass(frozen=True, slots=True)
class PromptValidationReport:
    """Every problem `PromptValidator` found, in check order."""

    issues: tuple[PromptValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the prompt has zero `ERROR`-severity issues. `WARNING`s don't affect this."""
        return not any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[PromptValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[PromptValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.WARNING)


#: Sections `_check_required_sections_exist`/`_check_no_empty_required_section` require.
_REQUIRED_SECTIONS: tuple[SectionName, ...] = (
    SectionName.SYSTEM,
    SectionName.CONSTRAINT,
    SectionName.OUTPUT_FORMAT,
)


class PromptValidator:
    """Runs deterministic content-quality checks against a compiled prompt's sections."""

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self._max_tokens = max_tokens

    def validate(self, sections: Sequence[PromptSection]) -> PromptValidationReport:
        """Validate `sections` (typically `CompiledPrompt.all_sections()`)."""
        issues: list[PromptValidationIssue] = []
        issues.extend(self._check_not_empty(sections))
        issues.extend(self._check_required_sections_exist(sections))
        issues.extend(self._check_no_duplicate_examples(sections))
        issues.extend(self._check_token_budget(sections))
        issues.extend(self._check_no_empty_required_section(sections))
        return PromptValidationReport(issues=tuple(issues))

    @staticmethod
    def _check_not_empty(sections: Sequence[PromptSection]) -> list[PromptValidationIssue]:
        combined = "".join(section.content for section in sections).strip()
        if combined:
            return []
        return [
            PromptValidationIssue(
                rule="not_empty",
                severity=ValidationSeverity.ERROR,
                message="The compiled prompt has no content in any section.",
            )
        ]

    @staticmethod
    def _check_required_sections_exist(
        sections: Sequence[PromptSection],
    ) -> list[PromptValidationIssue]:
        present = {section.name for section in sections}
        issues: list[PromptValidationIssue] = []
        for required_name in _REQUIRED_SECTIONS:
            if required_name not in present:
                issues.append(
                    PromptValidationIssue(
                        rule="required_sections_exist",
                        severity=ValidationSeverity.ERROR,
                        message=f"Required section {required_name.value!r} is missing.",
                        section=required_name,
                    )
                )
        return issues

    @staticmethod
    def _check_no_duplicate_examples(
        sections: Sequence[PromptSection],
    ) -> list[PromptValidationIssue]:
        issues: list[PromptValidationIssue] = []
        for section in sections:
            if not isinstance(section, ExampleSection):
                continue
            seen: set[str] = set()
            for example_id in section.example_ids:
                if example_id in seen:
                    issues.append(
                        PromptValidationIssue(
                            rule="no_duplicate_examples",
                            severity=ValidationSeverity.ERROR,
                            message=f"Example {example_id!r} appears more than once in the retrieved examples section.",
                            section=SectionName.RETRIEVED_EXAMPLES,
                        )
                    )
                seen.add(example_id)
        return issues

    def _check_token_budget(self, sections: Sequence[PromptSection]) -> list[PromptValidationIssue]:
        total = sum(section.estimated_tokens for section in sections)
        if total <= self._max_tokens:
            return []
        return [
            PromptValidationIssue(
                rule="token_budget",
                severity=ValidationSeverity.ERROR,
                message=f"Estimated {total} tokens exceeds the {self._max_tokens} token budget.",
            )
        ]

    @staticmethod
    def _check_no_empty_required_section(
        sections: Sequence[PromptSection],
    ) -> list[PromptValidationIssue]:
        issues: list[PromptValidationIssue] = []
        for section in sections:
            if section.is_required and not section.content.strip():
                issues.append(
                    PromptValidationIssue(
                        rule="no_empty_required_section",
                        severity=ValidationSeverity.ERROR,
                        message=f"Required section {section.name.value!r} is empty.",
                        section=section.name,
                    )
                )
        return issues
