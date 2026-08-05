"""Shared fixtures and builders for SQL Repair Engine tests.

`metadata_registry`/`business_knowledge_registry`/`relationship_graph`
are built from QueryMind's real, shipped schema and business-knowledge
data (session-scoped, mirroring `tests/sql_validation/conftest.py`
exactly) so validator-adjacent behavior is exercised against the real
`customers`/`orders`/... schema. Everything else (bundle, GeneratedSQL,
SQLValidationResult, scripted LLM) is built synthetically for precise,
fast, isolated control — never a real network call.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.adapter import LLMAdapter
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.metadata.models import ColumnMetadata, PrimaryKeyMetadata, TableMetadata
from querymind.metadata.relationships import RelationshipGraph
from querymind.models.base import Base
from querymind.nlu.models import AggregationType, Intent, QueryContext
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import (
    RetrievalStatistics,
    RetrievedExample,
    RetrievedKnowledgeBundle,
    SignalBreakdown,
    SignalName,
)
from querymind.schema_linker.models import (
    LinkedQueryContext,
    MatchTier,
    ResolvedMetric,
    ResolvedTable,
)
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
)


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


# --- synthetic RetrievedKnowledgeBundle (mirrors tests/retrieval/conftest.py) -----------

_CUSTOMERS_TABLE = TableMetadata(
    name="customers",
    columns=(
        ColumnMetadata(
            table_name="customers",
            name="customer_id",
            sql_type="INTEGER",
            python_type="int",
            nullable=False,
            primary_key=True,
            unique=True,
            autoincrement=True,
        ),
    ),
    primary_key=PrimaryKeyMetadata(name="pk_customers", columns=("customer_id",)),
)


def make_query_context(**overrides: object) -> QueryContext:
    defaults: dict[str, object] = {
        "original_question": "Who are our top 10 customers by revenue?",
        "normalized_question": "who are our top 10 customers by revenue",
        "intent": Intent.TOP_N,
        "business_concepts": ("customer", "revenue"),
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return QueryContext(**defaults)  # type: ignore[arg-type]


def make_linked_context(**overrides: object) -> LinkedQueryContext:
    defaults: dict[str, object] = {
        "query_context": make_query_context(),
        "primary_entity": ResolvedTable(
            business_concept="customer",
            table=_CUSTOMERS_TABLE,
            confidence=1.0,
            matching_reason=MatchTier.EXACT,
            candidate_rank=1,
        ),
        "metrics": (
            ResolvedMetric(
                business_concept="revenue",
                column=ColumnMetadata(
                    table_name="orders",
                    name="total_amount",
                    sql_type="NUMERIC",
                    python_type="Decimal",
                    nullable=False,
                    primary_key=False,
                    unique=False,
                    autoincrement=False,
                ),
                aggregation=AggregationType.SUM,
                raw_text="revenue",
                confidence=0.85,
                matching_reason=MatchTier.SYNONYM,
                candidate_rank=1,
            ),
        ),
    }
    defaults.update(overrides)
    return LinkedQueryContext(**defaults)  # type: ignore[arg-type]


def make_retrieved_example(**overrides: object) -> RetrievedExample:
    from querymind.query_library.models import (
        Difficulty,
        QueryContextSummary,
        QueryExample,
        ResultShape,
    )

    example = QueryExample(
        id="top_customers_by_revenue",
        title="Top 10 Customers by Revenue",
        natural_language_question="Who are our top 10 customers by total revenue?",
        normalized_question="who are our top 10 customers by total revenue",
        query_context=QueryContextSummary(
            intent="top_n", primary_entity="customer", metrics=("revenue",), aggregation="sum"
        ),
        business_concepts=("revenue", "top_customer"),
        linked_schema_objects=("orders.total_amount", "customers.customer_id"),
        gold_sql=(
            "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
            "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
            "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
        ),
        sql_explanation="Joins customers to orders and sums revenue per customer.",
        difficulty=Difficulty.INTERMEDIATE,
        tags=("customers", "top-n", "joins"),
        expected_result_description="Up to 10 customers ranked by revenue.",
        expected_result_shape=ResultShape.RANKED_LIST,
    )
    defaults: dict[str, object] = {
        "example": example,
        "overall_score": 0.9,
        "signal_breakdown": (
            SignalBreakdown(
                signal=SignalName.BUSINESS_CONCEPT_OVERLAP,
                score=0.9,
                weight=0.3,
                weighted_score=0.27,
                detail="Shared concepts.",
            ),
        ),
        "selection_explanation": "Closely matches on business concepts.",
    }
    defaults.update(overrides)
    return RetrievedExample(**defaults)  # type: ignore[arg-type]


def make_bundle(**overrides: object) -> RetrievedKnowledgeBundle:
    defaults: dict[str, object] = {
        "linked_query_context": make_linked_context(),
        "retrieved_examples": (make_retrieved_example(),),
        "statistics": RetrievalStatistics(
            retrieval_latency_ms=1.0, top_k=5, candidate_count=25, average_score=0.9
        ),
    }
    defaults.update(overrides)
    return RetrievedKnowledgeBundle(**defaults)  # type: ignore[arg-type]


# --- GeneratedSQL / SQLValidationResult builders ----------------------------------------


def make_generated_sql(sql: str, *, dialect: SQLDialect = SQLDialect.POSTGRESQL) -> GeneratedSQL:
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


def make_validation_result(
    generated_sql: GeneratedSQL,
    *,
    errors: tuple[ValidationIssue, ...] = (),
    warnings: tuple[ValidationIssue, ...] = (),
) -> SQLValidationResult:
    return SQLValidationResult(
        generated_sql=generated_sql,
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_tables=(),
        validated_columns=(),
        validated_functions=(),
        validation_statistics=ValidationStatistics(
            validation_latency_ms=1.0,
            validator_execution_times=(),
            table_count=0,
            column_count=0,
            join_count=0,
            function_count=0,
            error_count=len(errors),
            warning_count=len(warnings),
        ),
    )


def make_issue(
    code: str,
    *,
    message: str | None = None,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message=message or f"{code} occurred.")


# --- Scripted LLM (mirrors tests/llm and tests/sql_generation conftest patterns) --------


class ScriptedProvider:
    """A `ProviderClient` that returns/raises a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[LLMResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_llm_response(*, content: str = "SELECT 1;", **overrides: object) -> LLMResponse:
    defaults: dict[str, object] = {
        "content": content,
        "metrics": GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=100.0,
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
    }
    defaults.update(overrides)
    return LLMResponse(**defaults)  # type: ignore[arg-type]


def make_llm_provider_config(**overrides: object) -> LLMProviderConfig:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "api_key": SecretStr("test-api-key"),
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)  # type: ignore[arg-type]


def make_llm_adapter(outcomes: list[LLMResponse | Exception]) -> LLMAdapter:
    """Build a real `LLMAdapter` wired with a `ScriptedProvider` returning `outcomes` in order."""
    return LLMAdapter(ScriptedProvider(outcomes), make_llm_provider_config())


@pytest.fixture
def bundle() -> RetrievedKnowledgeBundle:
    return make_bundle()
