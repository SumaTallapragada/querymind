"""Tests for `querymind.prompt_compiler.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.prompt_compiler.models import (
    NOT_TRIMMABLE_PRIORITY,
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptStatistics,
    PromptTemplate,
    RelationshipSection,
    SchemaSection,
    SectionName,
    SectionSpec,
    SectionTokenUsage,
    SystemSection,
)
from querymind.prompt_compiler.templates import DefaultPromptTemplate
from querymind.query_library.models import SQLDialect


def _statistics() -> PromptStatistics:
    return PromptStatistics(
        estimated_total_tokens=10,
        section_token_usage=(),
        retrieved_example_count=0,
        schema_object_count=0,
        compilation_latency_ms=0.5,
    )


def _compiled_prompt(**overrides: object) -> CompiledPrompt:
    defaults: dict[str, object] = {
        "system": SystemSection(content="sys", estimated_tokens=1),
        "business_context": BusinessSection(content="biz", estimated_tokens=1),
        "schema_context": SchemaSection(
            content="schema", estimated_tokens=1, schema_objects=("t",)
        ),
        "relationships": RelationshipSection(content="rel", estimated_tokens=1),
        "examples": ExampleSection(content="ex", estimated_tokens=1, example_ids=("e1",)),
        "constraints": ConstraintSection(content="con", estimated_tokens=1),
        "output_format": OutputSection(content="out", estimated_tokens=1),
        "statistics": _statistics(),
        "template_version": "1.0.0",
        "dialect": SQLDialect.POSTGRESQL,
    }
    defaults.update(overrides)
    return CompiledPrompt(**defaults)  # type: ignore[arg-type]


#: A custom template whose headers are deliberately unlike `DefaultPromptTemplate`'s,
#: so a test can prove `as_text()` is (or isn't) actually using it.
_CUSTOM_TEMPLATE = PromptTemplate(
    version="9.9.9-custom",
    name="custom",
    section_specs=(
        SectionSpec(name=SectionName.SYSTEM, header="# CUSTOM SYSTEM HEADER", order=1),
        SectionSpec(name=SectionName.BUSINESS_CONTEXT, header="## Business Context", order=2),
        SectionSpec(name=SectionName.SCHEMA_CONTEXT, header="## Schema Context", order=3),
        SectionSpec(name=SectionName.RELATIONSHIP, header="## Table Relationships", order=4),
        SectionSpec(
            name=SectionName.RETRIEVED_EXAMPLES, header="## CUSTOM EXAMPLES HEADER", order=5
        ),
        SectionSpec(name=SectionName.CONSTRAINT, header="## CUSTOM CONSTRAINTS HEADER", order=6),
        SectionSpec(name=SectionName.OUTPUT_FORMAT, header="## Output Format", order=7),
    ),
)


class TestSectionDefaults:
    def test_system_section_is_required_and_not_trimmable(self) -> None:
        section = SystemSection(content="x", estimated_tokens=1)
        assert section.name is SectionName.SYSTEM
        assert section.is_required is True
        assert section.priority == NOT_TRIMMABLE_PRIORITY

    def test_constraint_and_output_sections_are_required(self) -> None:
        assert ConstraintSection(content="x", estimated_tokens=1).is_required is True
        assert OutputSection(content="x", estimated_tokens=1).is_required is True

    def test_business_schema_relationship_example_sections_are_not_required(self) -> None:
        assert BusinessSection(content="x", estimated_tokens=1).is_required is False
        assert SchemaSection(content="x", estimated_tokens=1).is_required is False
        assert RelationshipSection(content="x", estimated_tokens=1).is_required is False
        assert ExampleSection(content="x", estimated_tokens=1).is_required is False

    def test_example_section_defaults_to_empty_example_ids(self) -> None:
        assert ExampleSection(content="x", estimated_tokens=1).example_ids == ()

    def test_schema_section_defaults_to_empty_schema_objects(self) -> None:
        assert SchemaSection(content="x", estimated_tokens=1).schema_objects == ()


class TestImmutability:
    def test_sections_are_frozen(self) -> None:
        section = SystemSection(content="x", estimated_tokens=1)
        with pytest.raises(ValidationError):
            section.content = "y"  # type: ignore[misc]

    def test_compiled_prompt_is_frozen(self) -> None:
        prompt = _compiled_prompt()
        with pytest.raises(ValidationError):
            prompt.template_version = "2.0.0"  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SystemSection(content="x", estimated_tokens=1, bogus_field="nope")  # type: ignore[call-arg]


class TestCompiledPrompt:
    def test_all_sections_returns_all_seven_in_pipeline_order(self) -> None:
        prompt = _compiled_prompt()
        sections = prompt.all_sections()
        assert len(sections) == 7
        assert [s.name for s in sections] == [
            SectionName.SYSTEM,
            SectionName.BUSINESS_CONTEXT,
            SectionName.SCHEMA_CONTEXT,
            SectionName.RELATIONSHIP,
            SectionName.RETRIEVED_EXAMPLES,
            SectionName.CONSTRAINT,
            SectionName.OUTPUT_FORMAT,
        ]

    def test_as_text_renders_via_the_formatter(self) -> None:
        prompt = _compiled_prompt()
        text = prompt.as_text()
        assert "sys" in text
        assert "out" in text

    def test_template_defaults_to_default_prompt_template_when_not_given(self) -> None:
        # Backward compatibility: every existing CompiledPrompt(...) construction across
        # the codebase omits `template=` -- it must keep working exactly as before.
        prompt = _compiled_prompt()
        assert prompt.template == DefaultPromptTemplate()

    def test_default_prompt_template_still_renders_correctly(self) -> None:
        prompt = _compiled_prompt()
        text = prompt.as_text()
        assert "# System Instructions" in text
        assert "## Similar Examples" in text
        assert "## Constraints" in text

    def test_as_text_preserves_the_template_used_during_compilation(self) -> None:
        # The core fix: as_text() must render with *this* CompiledPrompt's own
        # template, not silently substitute DefaultPromptTemplate.
        prompt = _compiled_prompt(template=_CUSTOM_TEMPLATE)
        text = prompt.as_text()
        assert "# CUSTOM SYSTEM HEADER" in text
        assert "## CUSTOM EXAMPLES HEADER" in text
        assert "## CUSTOM CONSTRAINTS HEADER" in text

    def test_as_text_never_silently_falls_back_to_default_template_when_a_custom_one_was_used(
        self,
    ) -> None:
        # Regression test for the original Phase 12 bug: a CompiledPrompt built with a
        # custom template must never show DefaultPromptTemplate's generic headers.
        prompt = _compiled_prompt(template=_CUSTOM_TEMPLATE)
        text = prompt.as_text()
        assert "## Similar Examples" not in text
        assert "## Constraints" not in text

    def test_template_field_is_the_actual_template_object_not_just_a_version_string(self) -> None:
        prompt = _compiled_prompt(template=_CUSTOM_TEMPLATE)
        assert prompt.template == _CUSTOM_TEMPLATE
        assert prompt.template.spec_for(SectionName.SYSTEM).header == "# CUSTOM SYSTEM HEADER"


class TestSectionTokenUsage:
    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(ValidationError):
            SectionTokenUsage(section=SectionName.SYSTEM, estimated_tokens=-1)
