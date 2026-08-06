"""Shared fixtures and builders for End-to-End QueryMind Orchestrator tests.

Mirrors `tests/sql_repair/conftest.py`/`tests/sql_repair/test_integration.py`'s
"real everything, mocked network only" precedent: `metadata_registry`/
`business_knowledge_registry`/`query_library` are built from QueryMind's
real, shipped data (session-scoped, read-only); `engine`/
`connection_provider` are the real, already-running local Postgres
instance (function-scoped -- see `tests/sql_execution/conftest.py`'s
`engine` fixture docstring for why session-scoped breaks across this
project's per-test event loops); the LLM's network transport is replaced
with `httpx.MockTransport` (per Phase 10B/11A/11B/12's precedent) so no
real API call is ever made.

`make_pipeline_runner` assembles a fully real `PipelineRunner` from all
of the above plus one caller-supplied `httpx` mock handler -- the single
seam every test actually varies. `test_integration.py` is the only user
of any of this.

Every other test file (`test_pipeline.py`, `test_engine.py`,
`test_models.py`, `test_statistics.py`, `test_serializer.py`) instead
uses the synthetic builders below (`make_query_context` through
`make_business_answer`) -- fast, deterministic, real (immutable, fully
validated) Pydantic model instances built directly, with no registry, no
database, and no network anywhere, mirroring `tests/sql_repair/conftest.py`
and `tests/sql_validation/conftest.py`'s own synthetic builders. This
package's OWN responsibility under test is orchestration -- sequencing
and branching -- not any individual phase's own algorithm, which that
phase's own test suite already covers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    TokenUsage,
)
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.metadata.models import ColumnMetadata, PrimaryKeyMetadata, TableMetadata
from querymind.models.base import Base
from querymind.nlu import QueryParser
from querymind.nlu.models import AggregationType, Intent, QueryContext
from querymind.nlu.time import DefaultTimeExtractor
from querymind.orchestrator.models import GeneratedSqlResult, PipelineStatistics
from querymind.orchestrator.pipeline import PipelineRunner
from querymind.prompt_compiler import PromptCompiler
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
from querymind.query_library import QueryLibraryRegistry
from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    ResultShape,
    SQLDialect,
)
from querymind.result_formatter import ResultFormatterEngine
from querymind.result_formatter.models import BusinessAnswer
from querymind.retrieval import RetrievalEngine
from querymind.retrieval.models import (
    RetrievalStatistics,
    RetrievedExample,
    RetrievedKnowledgeBundle,
    SignalBreakdown,
    SignalName,
)
from querymind.schema_linker import SchemaLinker
from querymind.schema_linker.models import (
    LinkedQueryContext,
    MatchTier,
    ResolvedMetric,
    ResolvedTable,
)
from querymind.sql_execution import DatabaseConnectionProvider, SQLExecutionEngine
from querymind.sql_execution.models import (
    ExecutionError,
    ExecutionStatistics,
    ExecutionStatus,
    QueryColumn,
    QueryResult,
    QueryRow,
    SQLExecutionResult,
)
from querymind.sql_generation import SQLGenerationEngine
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_repair import SQLRepairEngine, SQLRepairLLMAdapter
from querymind.sql_repair.models import (
    RepairHistory,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation import SQLValidationEngine
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
)

# --- real, shipped, read-only data ---------------------------------------------------------


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
def query_library() -> QueryLibraryRegistry:
    registry = QueryLibraryRegistry()
    registry.load()
    return registry


# --- real database engine / connection provider ---------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped -- see `tests/sql_execution/conftest.py`'s `engine` fixture docstring
    for why a session-scoped `AsyncEngine` breaks across this project's per-test event loops."""
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def connection_provider(engine: AsyncEngine) -> DatabaseConnectionProvider:
    return DatabaseConnectionProvider(engine)


# --- mocked LLM transport --------------------------------------------------------------------


def claude_success_body(text: str) -> dict[str, object]:
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


def sequential_sql_handler(sql_texts: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    """Return a mock transport handler that replies with `sql_texts` in order, one per call.

    Used to script a first (broken) SQL generation followed by a second
    (repaired) response, exactly as `SQLGenerationEngine` then, if
    needed, `SQLRepairEngine` would each separately call the same
    underlying `LLMAdapter`.
    """
    remaining = list(sql_texts)

    def handler(request: httpx.Request) -> httpx.Response:
        text = remaining.pop(0)
        return httpx.Response(200, json=claude_success_body(f"```sql\n{text}\n```"))

    return handler


def make_llm_provider_config(**overrides: object) -> LLMProviderConfig:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "api_key": SecretStr("test-api-key"),
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)  # type: ignore[arg-type]


def build_llm_adapter(handler: Callable[[httpx.Request], httpx.Response]) -> LLMAdapter:
    """Build a real `LLMAdapter`/`ClaudeProvider` whose network is replaced by `handler`."""
    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = make_llm_provider_config()
    provider = ClaudeProvider(config, transport=transport)
    return LLMAdapter(provider, config)


# --- fully-wired PipelineRunner --------------------------------------------------------------


def make_pipeline_runner(
    *,
    handler: Callable[[httpx.Request], httpx.Response],
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    query_library: QueryLibraryRegistry,
    connection_provider: DatabaseConnectionProvider,
    dialect: SQLDialect = SQLDialect.POSTGRESQL,
) -> PipelineRunner:
    """Assemble a fully real `PipelineRunner` -- every collaborator is a real phase engine.

    The only seam is `handler`, the mock transport handler standing in
    for the network the real `LLMAdapter`/`ClaudeProvider` would
    otherwise call.
    """
    llm_adapter = build_llm_adapter(handler)
    validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)

    return PipelineRunner(
        nlu_parser=QueryParser(
            time_extractor=DefaultTimeExtractor(reference_date=date(2026, 8, 3))
        ),
        schema_linker=SchemaLinker(metadata_registry),
        business_knowledge_registry=business_knowledge_registry,
        retrieval_engine=RetrievalEngine(
            query_library=query_library, business_knowledge=business_knowledge_registry
        ),
        prompt_compiler=PromptCompiler(),
        sql_generation_engine=SQLGenerationEngine(llm_adapter),
        sql_validation_engine=validation_engine,
        sql_repair_engine=SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter), RepairValidator(validation_engine)
        ),
        sql_execution_engine=SQLExecutionEngine(connection_provider),
        result_formatter_engine=ResultFormatterEngine(),
        dialect=dialect,
    )


# --- synthetic model builders (mirrors tests/sql_repair/conftest.py + tests/sql_validation/conftest.py) --

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


def make_compiled_prompt(**overrides: object) -> CompiledPrompt:
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


def make_repair_result(
    original_sql: GeneratedSQL,
    final_sql: GeneratedSQL,
    final_validation_result: SQLValidationResult,
    *,
    status: RepairStatus = RepairStatus.REPAIRED,
    attempt_count: int = 1,
) -> SQLRepairResult:
    return SQLRepairResult(
        original_sql=original_sql,
        final_sql=final_sql,
        final_validation_result=final_validation_result,
        history=RepairHistory(attempts=()),
        statistics=RepairStatistics(
            attempt_count=attempt_count,
            successful_repairs=1 if status is RepairStatus.REPAIRED else 0,
            failed_repairs=0 if status is RepairStatus.REPAIRED else attempt_count,
            repair_latency_ms=1.0,
            average_validation_latency_ms=1.0,
        ),
        status=status,
    )


def make_execution_result(
    generated_sql: GeneratedSQL,
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    error: ExecutionError | None = None,
) -> SQLExecutionResult:
    query_result: QueryResult | None = None
    if status is ExecutionStatus.SUCCESS:
        query_result = QueryResult(
            columns=(QueryColumn(name="customer_id", database_type="bigint", python_type="int"),),
            rows=(QueryRow(values=(1,)),),
            row_count=1,
        )
    return SQLExecutionResult(
        status=status,
        executed_sql=generated_sql.sql,
        query_result=query_result,
        statistics=ExecutionStatistics(
            execution_latency_ms=1.0,
            rows_returned=query_result.row_count if query_result is not None else 0,
            columns_returned=len(query_result.columns) if query_result is not None else 0,
            database_name="querymind",
            dialect=generated_sql.dialect,
        ),
        execution_error=error,
    )


def make_business_answer(execution_result: SQLExecutionResult) -> BusinessAnswer:
    """Build a real `BusinessAnswer` via the real `ResultFormatterEngine` -- never hand-built."""
    return ResultFormatterEngine().format(execution_result)


def make_generated_sql_result(
    generated_sql: GeneratedSQL,
    validation_result: SQLValidationResult,
    *,
    repair_result: SQLRepairResult | None = None,
) -> GeneratedSqlResult:
    return GeneratedSqlResult(
        original_question="Who are our top customers by revenue?",
        generated_sql=generated_sql,
        validation_result=validation_result,
        repair_result=repair_result,
        statistics=PipelineStatistics(
            total_latency_ms=10.0, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
    )
