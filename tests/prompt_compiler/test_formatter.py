"""Tests for `querymind.prompt_compiler.formatter`."""

from __future__ import annotations

from querymind.prompt_compiler.formatter import PromptFormatter
from querymind.prompt_compiler.models import (
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


def _prompt(**overrides: object) -> CompiledPrompt:
    defaults: dict[str, object] = {
        "system": SystemSection(content="System text.", estimated_tokens=1),
        "business_context": BusinessSection(content="Business text.", estimated_tokens=1),
        "schema_context": SchemaSection(content="Schema text.", estimated_tokens=1),
        "relationships": RelationshipSection(content="Relationship text.", estimated_tokens=1),
        "examples": ExampleSection(content="Example text.", estimated_tokens=1),
        "constraints": ConstraintSection(content="Constraint text.", estimated_tokens=1),
        "output_format": OutputSection(content="Output text.", estimated_tokens=1),
        "statistics": _statistics(),
        "template_version": "1.0.0",
        "dialect": SQLDialect.POSTGRESQL,
    }
    defaults.update(overrides)
    return CompiledPrompt(**defaults)  # type: ignore[arg-type]


class TestFormat:
    def test_renders_every_section_with_its_header_in_template_order(self) -> None:
        text = PromptFormatter().format(_prompt())
        assert text.index("# System Instructions") < text.index("System text.")
        assert text.index("## Business Context") < text.index("## Schema Context")
        assert text.index("## Schema Context") < text.index("## Table Relationships")
        assert text.index("## Table Relationships") < text.index("## Similar Examples")
        assert text.index("## Similar Examples") < text.index("## Constraints")
        assert text.index("## Constraints") < text.index("## Output Format")

    def test_skips_sections_with_blank_content(self) -> None:
        prompt = _prompt(business_context=BusinessSection(content="   ", estimated_tokens=0))
        text = PromptFormatter().format(prompt)
        assert "## Business Context" not in text

    def test_sections_are_separated_by_a_blank_line(self) -> None:
        text = PromptFormatter().format(_prompt())
        assert "\n\n" in text

    def test_uses_a_custom_template_when_given(self) -> None:
        template = PromptTemplate(
            version="0.1.0",
            name="system-only",
            section_specs=(SectionSpec(name=SectionName.SYSTEM, header="# Only System", order=1),),
        )
        text = PromptFormatter(template).format(_prompt())
        assert "# Only System" in text
        assert "## Business Context" not in text
        assert "Business text." not in text

    def test_default_template_is_used_when_none_given(self) -> None:
        default_text = PromptFormatter().format(_prompt())
        explicit_text = PromptFormatter(DefaultPromptTemplate()).format(_prompt())
        assert default_text == explicit_text
