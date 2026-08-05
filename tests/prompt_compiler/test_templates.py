"""Tests for `querymind.prompt_compiler.templates`."""

from __future__ import annotations

import pytest

from querymind.prompt_compiler.exceptions import PromptCompilationError
from querymind.prompt_compiler.models import PromptTemplate, SectionName, SectionSpec
from querymind.prompt_compiler.templates import DefaultPromptTemplate


class TestDefaultPromptTemplate:
    def test_has_all_seven_sections(self) -> None:
        template = DefaultPromptTemplate()
        names = {spec.name for spec in template.section_specs}
        assert names == set(SectionName)

    def test_ordered_names_matches_the_pipeline_order(self) -> None:
        template = DefaultPromptTemplate()
        assert template.ordered_names() == (
            SectionName.SYSTEM,
            SectionName.BUSINESS_CONTEXT,
            SectionName.SCHEMA_CONTEXT,
            SectionName.RELATIONSHIP,
            SectionName.RETRIEVED_EXAMPLES,
            SectionName.CONSTRAINT,
            SectionName.OUTPUT_FORMAT,
        )

    def test_spec_for_returns_the_matching_spec(self) -> None:
        template = DefaultPromptTemplate()
        spec = template.spec_for(SectionName.SCHEMA_CONTEXT)
        assert spec.header == "## Schema Context"
        assert spec.order == 3

    def test_version_and_name(self) -> None:
        template = DefaultPromptTemplate()
        assert template.version == "1.0.0"
        assert template.name == "default"


class TestPromptTemplate:
    def test_spec_for_raises_when_section_not_in_template(self) -> None:
        template = PromptTemplate(
            version="0.1.0",
            name="partial",
            section_specs=(SectionSpec(name=SectionName.SYSTEM, header="# System", order=1),),
        )
        with pytest.raises(PromptCompilationError):
            template.spec_for(SectionName.SCHEMA_CONTEXT)

    def test_ordered_names_respects_custom_order(self) -> None:
        template = PromptTemplate(
            version="0.1.0",
            name="reversed",
            section_specs=(
                SectionSpec(name=SectionName.OUTPUT_FORMAT, header="# Output", order=1),
                SectionSpec(name=SectionName.SYSTEM, header="# System", order=2),
            ),
        )
        assert template.ordered_names() == (SectionName.OUTPUT_FORMAT, SectionName.SYSTEM)

    def test_section_spec_include_by_default_defaults_true(self) -> None:
        spec = SectionSpec(name=SectionName.SYSTEM, header="# System", order=1)
        assert spec.include_by_default is True
