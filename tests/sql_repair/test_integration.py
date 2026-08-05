"""End-to-end tests against the real, fully wired repair stack.

Wires `SQLRepairEngine` on top of the real `MetadataRegistry`/
`BusinessKnowledgeRegistry`/`SQLValidationEngine`, a real
`RetrievalEngine`-produced `RetrievedKnowledgeBundle` (via the real
NLU -> Schema Linker -> Retrieval chain, mirroring
`tests/sql_validation/test_integration.py`'s precedent), and a real
`LLMAdapter`/`ClaudeProvider` with the network replaced by
`httpx.MockTransport` (per Phase 10B/11A/11B's precedent) -- so a
genuinely broken, real query is repaired through the same components
production would use.
"""

from __future__ import annotations

from datetime import date

import httpx
from pydantic import SecretStr

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata.registry import MetadataRegistry
from querymind.nlu import QueryParser
from querymind.nlu.time import DefaultTimeExtractor
from querymind.query_library import QueryLibraryRegistry
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker
from querymind.sql_repair.engine import SQLRepairEngine
from querymind.sql_repair.llm_adapter import SQLRepairLLMAdapter
from querymind.sql_repair.models import RepairStatus
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation.engine import SQLValidationEngine

from .conftest import make_generated_sql, make_llm_provider_config

_BROKEN_SQL = (
    "SELECT c.customer_id, w.warehouse_id "
    "FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
)
_FIXED_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
)


def _claude_success_body(text: str) -> dict[str, object]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 200, "output_tokens": 50},
    }


def test_a_hallucinated_join_is_repaired_end_to_end(
    metadata_registry: MetadataRegistry, business_knowledge_registry: BusinessKnowledgeRegistry
) -> None:
    query_library = QueryLibraryRegistry()
    query_library.load()
    retrieval_engine = RetrievalEngine(
        query_library=query_library, business_knowledge=business_knowledge_registry
    )
    linker = SchemaLinker(metadata_registry)
    parser = QueryParser(time_extractor=DefaultTimeExtractor(reference_date=date(2026, 8, 3)))

    context = parser.parse("Who are our top 10 customers by revenue?")
    linked = linker.link(context)
    bundle = retrieval_engine.retrieve(linked, top_k=3)

    generated = make_generated_sql(_BROKEN_SQL)
    validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
    validation_result = validation_engine.validate(generated)
    assert validation_result.is_valid is False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_claude_success_body(f"```sql\n{_FIXED_SQL}\n```"))

    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = make_llm_provider_config(api_key=SecretStr("test-key"))
    provider = ClaudeProvider(config, transport=transport)
    llm_adapter = LLMAdapter(provider, config)

    engine = SQLRepairEngine(SQLRepairLLMAdapter(llm_adapter), RepairValidator(validation_engine))
    result = engine.repair(generated, validation_result, bundle)

    assert result.status is RepairStatus.REPAIRED
    assert result.final_validation_result.is_valid is True
    assert result.final_sql.sql == _FIXED_SQL
    assert result.original_sql.sql == _BROKEN_SQL
    assert result.statistics.attempt_count == 1
