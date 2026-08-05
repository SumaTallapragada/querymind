"""Tests for `querymind.sql_repair.llm_adapter.SQLRepairLLMAdapter`."""

from __future__ import annotations

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
from querymind.query_library.models import SQLDialect
from querymind.sql_repair.llm_adapter import SQLRepairLLMAdapter

from .conftest import make_llm_adapter, make_llm_response


def _compiled_prompt() -> CompiledPrompt:
    return CompiledPrompt(
        system=SystemSection(content="sys", estimated_tokens=1),
        business_context=BusinessSection(content="biz", estimated_tokens=1),
        schema_context=SchemaSection(content="schema", estimated_tokens=1),
        relationships=RelationshipSection(content="rel", estimated_tokens=1),
        examples=ExampleSection(content="ex", estimated_tokens=1),
        constraints=ConstraintSection(content="con", estimated_tokens=1),
        output_format=OutputSection(content="out", estimated_tokens=1),
        statistics=PromptStatistics(
            estimated_total_tokens=7,
            section_token_usage=(),
            retrieved_example_count=0,
            schema_object_count=0,
            compilation_latency_ms=0.1,
        ),
        template_version="1.0.0-repair",
        dialect=SQLDialect.POSTGRESQL,
    )


class TestRepair:
    def test_calls_the_underlying_llm_adapter_and_returns_its_response(self) -> None:
        response = make_llm_response(content="SELECT 1;")
        adapter = make_llm_adapter([response])
        repair_adapter = SQLRepairLLMAdapter(adapter)

        result = repair_adapter.repair(_compiled_prompt())
        assert result.content == "SELECT 1;"

    def test_the_prompt_text_reaches_the_provider(self) -> None:
        adapter = make_llm_adapter([make_llm_response()])
        repair_adapter = SQLRepairLLMAdapter(adapter)
        prompt = _compiled_prompt()

        repair_adapter.repair(prompt)

        sent_request = adapter._provider_client.requests[0]  # type: ignore[attr-defined]
        assert sent_request.prompt == prompt.as_text()
