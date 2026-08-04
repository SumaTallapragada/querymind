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
    RelationshipSection,
    SchemaSection,
    SectionName,
    SectionTokenUsage,
    SystemSection,
)
from querymind.query_library.models import SQLDialect


def _statistics() -> PromptStatistics:
    return PromptStatistics(
        estimated_total_tokens=10,
        section_token_usage=(),
        retrieved_example_count=0,
        schema_object_count=0,
        compilation_latency_ms=0.5,
    )


def _compiled_prompt() -> CompiledPrompt:
    return CompiledPrompt(
        system=SystemSection(content="sys", estimated_tokens=1),
        business_context=BusinessSection(content="biz", estimated_tokens=1),
        schema_context=SchemaSection(content="schema", estimated_tokens=1, schema_objects=("t",)),
        relationships=RelationshipSection(content="rel", estimated_tokens=1),
        examples=ExampleSection(content="ex", estimated_tokens=1, example_ids=("e1",)),
        constraints=ConstraintSection(content="con", estimated_tokens=1),
        output_format=OutputSection(content="out", estimated_tokens=1),
        statistics=_statistics(),
        template_version="1.0.0",
        dialect=SQLDialect.POSTGRESQL,
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


class TestSectionTokenUsage:
    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(ValidationError):
            SectionTokenUsage(section=SectionName.SYSTEM, estimated_tokens=-1)
