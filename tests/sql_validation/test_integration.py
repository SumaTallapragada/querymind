"""End-to-end tests against the real, fully wired validation stack.

Wires `SQLGenerationEngine` -> `SQLValidationEngine` together, using the
real `MetadataRegistry`/`BusinessKnowledgeRegistry`/`RelationshipGraph`
and a real `LLMAdapter`/`ClaudeProvider` (network replaced with
`httpx.MockTransport`, per Phase 10B/11A's precedent) -- so the SQL fed
into validation is genuinely produced by the SQL Generation Engine, not
hand-constructed, and the validation runs against the actual project
schema and business-knowledge catalog.
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata.registry import MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.sql_generation.engine import SQLGenerationEngine
from querymind.sql_validation.engine import SQLValidationEngine

from .conftest import make_compiled_prompt


def _claude_response(text: str) -> dict[str, object]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 30},
    }


def _generation_engine_returning(text: str) -> SQLGenerationEngine:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_claude_response(text))

    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = LLMProviderConfig(model="claude-sonnet-5", api_key=SecretStr("test-key"))
    provider = ClaudeProvider(config, transport=transport)
    return SQLGenerationEngine(LLMAdapter(provider, config))


def test_a_correct_llm_generated_query_validates_successfully(
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    relationship_graph: RelationshipGraph,
) -> None:
    text = (
        "```sql\n"
        "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue\n"
        "FROM customers c\n"
        "JOIN orders o ON o.customer_id = c.customer_id\n"
        "GROUP BY c.customer_id\n"
        "ORDER BY total_revenue DESC\n"
        "LIMIT 10\n"
        "```"
    )
    generation_engine = _generation_engine_returning(text)
    validation_engine = SQLValidationEngine(
        metadata_registry, business_knowledge_registry, relationship_graph
    )

    generated = generation_engine.generate(make_compiled_prompt())
    result = validation_engine.validate(generated)

    assert result.is_valid is True
    assert "customers" in result.validated_tables
    assert "orders" in result.validated_tables


def test_a_hallucinated_table_from_the_llm_is_caught(
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    relationship_graph: RelationshipGraph,
) -> None:
    text = "```sql\nSELECT * FROM this_table_does_not_exist;\n```"
    generation_engine = _generation_engine_returning(text)
    validation_engine = SQLValidationEngine(
        metadata_registry, business_knowledge_registry, relationship_graph
    )

    generated = generation_engine.generate(make_compiled_prompt())
    result = validation_engine.validate(generated)

    assert result.is_valid is False
    assert any(issue.code == "unknown_table" for issue in result.errors)


def test_an_unsupported_statement_from_the_llm_is_caught(
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    relationship_graph: RelationshipGraph,
) -> None:
    text = "```sql\nDELETE FROM customers;\n```"
    generation_engine = _generation_engine_returning(text)
    validation_engine = SQLValidationEngine(
        metadata_registry, business_knowledge_registry, relationship_graph
    )

    generated = generation_engine.generate(make_compiled_prompt())
    result = validation_engine.validate(generated)

    assert result.is_valid is False
    assert any(issue.code == "unsupported_statement_type" for issue in result.errors)
