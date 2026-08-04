"""Tests for `querymind.prompt_compiler.validator`."""

from __future__ import annotations

from querymind.prompt_compiler.models import (
    BusinessSection,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptSection,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.prompt_compiler.validator import PromptValidator, ValidationSeverity


def _valid_sections() -> tuple[PromptSection, ...]:
    return (
        SystemSection(content="sys", estimated_tokens=10),
        BusinessSection(content="biz", estimated_tokens=10),
        SchemaSection(content="schema", estimated_tokens=10, schema_objects=("t",)),
        RelationshipSection(content="rel", estimated_tokens=10),
        ExampleSection(content="ex", estimated_tokens=10, example_ids=("e1", "e2")),
        ConstraintSection(content="con", estimated_tokens=10),
        OutputSection(content="out", estimated_tokens=10),
    )


class TestValidPrompt:
    def test_fully_valid_sections_produce_no_errors(self) -> None:
        report = PromptValidator(max_tokens=4000).validate(_valid_sections())
        assert report.is_valid
        assert report.errors == ()


class TestNotEmpty:
    def test_flags_a_prompt_with_no_content_anywhere(self) -> None:
        sections = (SystemSection(content="", estimated_tokens=0),)
        report = PromptValidator().validate(sections)
        assert not report.is_valid
        assert any(issue.rule == "not_empty" for issue in report.errors)


class TestRequiredSectionsExist:
    def test_flags_a_missing_required_section(self) -> None:
        sections = tuple(s for s in _valid_sections() if not isinstance(s, ConstraintSection))
        report = PromptValidator().validate(sections)
        assert not report.is_valid
        issue = next(i for i in report.errors if i.rule == "required_sections_exist")
        assert issue.severity is ValidationSeverity.ERROR

    def test_does_not_flag_a_missing_optional_section(self) -> None:
        sections = tuple(s for s in _valid_sections() if not isinstance(s, BusinessSection))
        report = PromptValidator().validate(sections)
        assert not any(i.rule == "required_sections_exist" for i in report.issues)


class TestNoDuplicateExamples:
    def test_flags_duplicate_example_ids(self) -> None:
        sections = tuple(
            ExampleSection(content="ex", estimated_tokens=10, example_ids=("e1", "e1"))
            if isinstance(s, ExampleSection)
            else s
            for s in _valid_sections()
        )
        report = PromptValidator().validate(sections)
        assert not report.is_valid
        issue = next(i for i in report.errors if i.rule == "no_duplicate_examples")
        assert "e1" in issue.message

    def test_no_error_when_example_ids_are_unique(self) -> None:
        report = PromptValidator().validate(_valid_sections())
        assert not any(i.rule == "no_duplicate_examples" for i in report.issues)


class TestTokenBudget:
    def test_flags_prompt_exceeding_the_budget(self) -> None:
        report = PromptValidator(max_tokens=10).validate(_valid_sections())
        assert not report.is_valid
        assert any(i.rule == "token_budget" for i in report.errors)

    def test_no_error_when_within_budget(self) -> None:
        report = PromptValidator(max_tokens=4000).validate(_valid_sections())
        assert not any(i.rule == "token_budget" for i in report.issues)


class TestNoEmptyRequiredSection:
    def test_flags_an_empty_required_section(self) -> None:
        sections = tuple(
            SystemSection(content="", estimated_tokens=0) if isinstance(s, SystemSection) else s
            for s in _valid_sections()
        )
        report = PromptValidator().validate(sections)
        assert not report.is_valid
        issue = next(i for i in report.errors if i.rule == "no_empty_required_section")
        assert issue.section is not None

    def test_does_not_flag_an_empty_optional_section(self) -> None:
        sections = tuple(
            BusinessSection(content="", estimated_tokens=0) if isinstance(s, BusinessSection) else s
            for s in _valid_sections()
        )
        report = PromptValidator().validate(sections)
        assert not any(i.rule == "no_empty_required_section" for i in report.issues)


class TestReportProperties:
    def test_errors_and_warnings_partition_issues_by_severity(self) -> None:
        sections = (SystemSection(content="", estimated_tokens=0),)
        report = PromptValidator().validate(sections)
        assert all(i.severity is ValidationSeverity.ERROR for i in report.errors)
        assert all(i.severity is ValidationSeverity.WARNING for i in report.warnings)
        assert set(report.errors) | set(report.warnings) == set(report.issues)
