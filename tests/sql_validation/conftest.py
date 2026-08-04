"""Shared fixtures for SQL Validation Engine tests.

`metadata_registry`/`business_knowledge_registry`/`relationship_graph`
are built from QueryMind's real, shipped schema and business-knowledge
data (session-scoped since they're read-only and moderately expensive to
build) — every validator test runs against the actual `customers`/
`orders`/... schema, never a hand-rolled fake one, so a test failure
means something real about how the validator behaves against this
project's own data.
"""

from __future__ import annotations

import pytest

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.models.base import Base
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
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_validation.parser import ParsedSQL, SQLParser


@pytest.fixture(scope="session")
def metadata_registry() -> MetadataRegistry:
    registry = MetadataRegistry(MetadataExtractor(Base.registry), ColumnDictionary.default())
    registry.load()
    return registry


@pytest.fixture(scope="session")
def business_knowledge_registry() -> BusinessKnowledgeRegistry:
    registry = BusinessKnowledgeRegistry()
    registry.load()
    return registry


@pytest.fixture(scope="session")
def relationship_graph(metadata_registry: MetadataRegistry) -> RelationshipGraph:
    return metadata_registry.build_graph()


def parse(sql: str, *, dialect: str = "postgres") -> ParsedSQL:
    """Parse `sql` with the real `SQLParser` -- the shared entry point every validator test uses."""
    return SQLParser().parse(sql, dialect=dialect)


def make_compiled_prompt(**overrides: object) -> CompiledPrompt:
    """Build a minimal, realistic `CompiledPrompt` -- the input `SQLGenerationEngine.generate` needs."""
    defaults: dict[str, object] = {
        "system": SystemSection(content="You are a careful SQL assistant.", estimated_tokens=6),
        "business_context": BusinessSection(
            content="Concerns customer revenue.", estimated_tokens=4
        ),
        "schema_context": SchemaSection(
            content="Table `customers`.", estimated_tokens=3, schema_objects=("customers",)
        ),
        "relationships": RelationshipSection(content="No joins required.", estimated_tokens=3),
        "examples": ExampleSection(content="No examples.", estimated_tokens=2),
        "constraints": ConstraintSection(
            content="Return exactly one statement.", estimated_tokens=4
        ),
        "output_format": OutputSection(content="Write valid postgresql SQL.", estimated_tokens=4),
        "statistics": PromptStatistics(
            estimated_total_tokens=26,
            section_token_usage=(),
            retrieved_example_count=0,
            schema_object_count=1,
            compilation_latency_ms=0.2,
        ),
        "template_version": "1.0.0",
        "dialect": SQLDialect.POSTGRESQL,
    }
    defaults.update(overrides)
    return CompiledPrompt(**defaults)  # type: ignore[arg-type]


def make_generated_sql(sql: str, *, dialect: SQLDialect = SQLDialect.POSTGRESQL) -> GeneratedSQL:
    """Build a minimal, realistic `GeneratedSQL` wrapping `sql`."""
    return GeneratedSQL(
        sql=sql,
        statement_type=SQLStatementType.SELECT,
        raw_llm_content=sql,
        dialect=dialect,
        llm_metrics=GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=1.0,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
        statistics=SQLGenerationStatistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql_length=len(sql),
            normalized_sql_length=len(sql),
            normalization_changed_sql=False,
            generation_latency_ms=1.0,
        ),
    )
