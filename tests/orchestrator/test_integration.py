"""End-to-end tests against the real, fully wired QueryMind pipeline.

Wires `PipelineRunner`/`QueryMindEngine` on top of every real phase
engine -- real `MetadataRegistry`/`BusinessKnowledgeRegistry`/
`QueryLibraryRegistry`, real `SchemaLinker`/`RetrievalEngine`/
`PromptCompiler`/`SQLValidationEngine`/`SQLRepairEngine`, a real
`LLMAdapter`/`ClaudeProvider` with the network replaced by
`httpx.MockTransport` (per Phase 10B/11A/11B/12's precedent), and a real
`SQLExecutionEngine` against the real, already-running, seeded local
Postgres instance -- so a genuine natural language question is answered
through the same components production would use, end to end.
"""

from __future__ import annotations

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.metadata import MetadataRegistry
from querymind.orchestrator.engine import QueryMindEngine
from querymind.orchestrator.models import PipelineStage, PipelineStatus
from querymind.query_library import QueryLibraryRegistry
from querymind.result_formatter.models import AnswerType
from querymind.sql_execution import DatabaseConnectionProvider
from querymind.sql_repair.models import RepairStatus
from querymind.sql_validation import SQLValidationEngine

from .conftest import make_generated_sql, make_pipeline_runner, sequential_sql_handler

_VALID_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
)

# A JOIN between two tables with no relationship in the real schema -- guaranteed invalid,
# exactly as in tests/sql_repair/test_integration.py.
_BROKEN_SQL = (
    "SELECT c.customer_id, w.warehouse_id "
    "FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
)


class TestSuccessfulPipelineNoRepair:
    async def test_a_valid_question_produces_a_complete_business_answer(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        assert response.status is PipelineStatus.SUCCESS
        assert response.error is None
        assert response.repair_result is None
        assert response.statistics.repair_attempted is False
        assert response.statistics.repair_performed is False
        assert response.generated_sql is not None
        assert response.generated_sql.sql == _VALID_SQL
        assert response.validation_result is not None
        assert response.validation_result.is_valid is True

    async def test_no_phase_is_bypassed(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        stages_run = {timing.stage for timing in response.statistics.stage_timings}
        assert stages_run == set(PipelineStage) - {PipelineStage.SQL_REPAIR}

    async def test_the_business_answer_matches_the_real_executed_results(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        assert response.business_answer is not None
        assert response.execution_result is not None
        assert response.execution_result.query_result is not None
        assert (
            response.business_answer.statistics.rows_processed
            == response.execution_result.query_result.row_count
        )
        assert response.business_answer.answer_type is AnswerType.AGGREGATION
        formatted_rows = [
            tuple(v.original_value for v in row.values)
            for row in response.business_answer.formatted_table.rows
        ]
        real_rows = [row.values for row in response.execution_result.query_result.rows]
        assert formatted_rows == real_rows

    async def test_every_stage_timing_is_non_negative(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        assert len(response.statistics.stage_timings) == len(PipelineStage) - 1
        assert all(timing.latency_ms >= 0.0 for timing in response.statistics.stage_timings)
        assert response.statistics.total_latency_ms >= 0.0


class TestPipelineRequiringRepair:
    async def test_a_hallucinated_join_is_repaired_and_still_produces_a_business_answer(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_BROKEN_SQL, _VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        assert response.statistics.repair_attempted is True
        assert response.statistics.repair_performed is True
        assert response.repair_result is not None
        assert response.repair_result.status is RepairStatus.REPAIRED
        assert response.repair_result.original_sql.sql == _BROKEN_SQL
        # The SQL ultimately executed/reported must be the repaired SQL, never the broken one.
        assert response.generated_sql is not None
        assert response.generated_sql.sql == _VALID_SQL
        assert response.status is PipelineStatus.SUCCESS
        assert response.business_answer is not None

    async def test_repair_stage_has_its_own_timing_when_it_runs(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_BROKEN_SQL, _VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        response = await engine.ask("Who are our top 10 customers by revenue?")

        stages_run = {timing.stage for timing in response.statistics.stage_timings}
        assert stages_run == set(PipelineStage)


class TestAskForSql:
    async def test_a_valid_question_returns_sql_without_executing_it(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        result = await engine.ask_for_sql("Who are our top 10 customers by revenue?")

        assert result.generated_sql.sql == _VALID_SQL
        assert result.validation_result.is_valid is True
        assert result.repair_result is None
        stages_run = {timing.stage for timing in result.statistics.stage_timings}
        assert PipelineStage.SQL_EXECUTION not in stages_run
        assert PipelineStage.RESULT_FORMATTING not in stages_run

    async def test_a_hallucinated_join_is_repaired_without_executing_the_result(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_BROKEN_SQL, _VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        result = await engine.ask_for_sql("Who are our top 10 customers by revenue?")

        assert result.repair_result is not None
        assert result.repair_result.status is RepairStatus.REPAIRED
        assert result.generated_sql.sql == _VALID_SQL


class TestRepair:
    async def test_repairs_a_hallucinated_join_given_only_the_question_and_validation_result(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        # A second Claude response is scripted for repair_sql's own generation-free repair
        # call (SQLRepairEngine talks to the LLM directly, not through SQLGenerationEngine).
        runner = make_pipeline_runner(
            handler=sequential_sql_handler([_VALID_SQL]),
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            connection_provider=connection_provider,
        )
        engine = QueryMindEngine(runner)

        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        broken = make_generated_sql(_BROKEN_SQL)
        validation_result = validation_engine.validate(broken)
        assert validation_result.is_valid is False

        repair_result = await engine.repair(
            "Who are our top 10 customers by revenue?", validation_result
        )

        assert repair_result.status is RepairStatus.REPAIRED
        assert repair_result.final_sql.sql == _VALID_SQL
        assert repair_result.original_sql is broken
