"""Tests for `querymind.prompt_compiler.serializer`."""

from __future__ import annotations

import json

import yaml

from querymind.prompt_compiler.models import (
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptStatistics,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.prompt_compiler.serializer import PromptCompilerSerializer
from querymind.query_library.models import SQLDialect


def _compiled_prompt() -> CompiledPrompt:
    return CompiledPrompt(
        system=SystemSection(content="sys", estimated_tokens=1),
        business_context=BusinessSection(content="biz", estimated_tokens=1),
        schema_context=SchemaSection(content="schema", estimated_tokens=1, schema_objects=("t",)),
        relationships=RelationshipSection(content="rel", estimated_tokens=1),
        examples=ExampleSection(content="ex", estimated_tokens=1, example_ids=("e1",)),
        constraints=ConstraintSection(content="con", estimated_tokens=1),
        output_format=OutputSection(content="out", estimated_tokens=1),
        statistics=PromptStatistics(
            estimated_total_tokens=7,
            section_token_usage=(),
            retrieved_example_count=1,
            schema_object_count=1,
            compilation_latency_ms=0.1,
        ),
        template_version="1.0.0",
        dialect=SQLDialect.POSTGRESQL,
    )


class TestToDict:
    def test_returns_a_json_safe_dict(self) -> None:
        result = PromptCompilerSerializer.to_dict(_compiled_prompt())
        assert isinstance(result, dict)
        assert result["template_version"] == "1.0.0"
        assert result["dialect"] == "postgresql"
        assert result["schema_context"]["schema_objects"] == ["t"]

    def test_collections_become_lists(self) -> None:
        result = PromptCompilerSerializer.to_dict(_compiled_prompt())
        assert isinstance(result["examples"]["example_ids"], list)


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = PromptCompilerSerializer.to_json(_compiled_prompt())
        parsed = json.loads(text)
        assert parsed["template_version"] == "1.0.0"

    def test_default_indent_is_readable(self) -> None:
        text = PromptCompilerSerializer.to_json(_compiled_prompt())
        assert "\n" in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = PromptCompilerSerializer.to_yaml(_compiled_prompt())
        parsed = yaml.safe_load(text)
        assert parsed["template_version"] == "1.0.0"
        assert parsed["dialect"] == "postgresql"
