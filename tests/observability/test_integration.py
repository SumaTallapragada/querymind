"""End-to-end tests: every observability engine against the real, fully wired stack.

`TestDiagnosticsEngineIntegration`/`TestHealthCheckEngineIntegration` wire
every real collaborator (real registries, a real `LLMProviderConfig`, the
real database) -- no fakes. `TestStageInstrumentationWithARealCall` wraps
a genuinely running `nlu.QueryParser`. `TestObservabilityWithARealPipeline`
runs a real question through a real, fully-wired `orchestrator
.PipelineRunner` (mocked LLM transport, per this project's established
precedent) and feeds its real output through `InMemoryMetricsCollector`,
`PipelineProfiler`, and `BenchmarkRunner` -- demonstrating every
observability engine against genuine pipeline behavior, not synthetic
data.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import LLMProvider
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata import MetadataRegistry
from querymind.nlu import QueryParser
from querymind.nlu.time import DefaultTimeExtractor
from querymind.observability.benchmark import BenchmarkRunner
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.health import HealthCheckEngine
from querymind.observability.logger import InMemoryLogSink, StageInstrumentation, StructuredLogger
from querymind.observability.metrics import InMemoryMetricsCollector
from querymind.observability.models import DiagnosticStatus, HealthStatus, LogEventType
from querymind.observability.profiler import PipelineProfiler
from querymind.orchestrator import PipelineRunner, QueryMindEngine
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.result_formatter import ResultFormatterEngine
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker
from querymind.sql_execution import DatabaseConnectionProvider, SQLExecutionEngine
from querymind.sql_generation import SQLGenerationEngine
from querymind.sql_repair import SQLRepairEngine, SQLRepairLLMAdapter
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation import SQLValidationEngine

_VALID_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 5;"
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


def _build_pipeline_runner(
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    query_library: QueryLibraryRegistry,
    connection_provider: DatabaseConnectionProvider,
) -> PipelineRunner:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_claude_success_body(f"```sql\n{_VALID_SQL}\n```"))

    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = LLMProviderConfig(
        provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("test-api-key")
    )
    llm_adapter = LLMAdapter(ClaudeProvider(config, transport=transport), config)
    validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)

    return PipelineRunner(
        nlu_parser=QueryParser(
            time_extractor=DefaultTimeExtractor(reference_date=date(2026, 8, 6))
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
    )


class TestDiagnosticsEngineIntegration:
    async def test_a_fully_configured_engine_reports_pass_or_a_documented_warning(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        engine = DiagnosticsEngine(
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            prompt_compiler=PromptCompiler(),
            llm_provider_config=LLMProviderConfig(
                provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("real-key")
            ),
            connection_provider=connection_provider,
        )
        report = await engine.run()

        # cache_configuration is deliberately always WARNING (see diagnostics.py); every
        # other check must PASS when every real collaborator is genuinely configured.
        for finding in report.findings:
            if finding.check_name == "cache_configuration":
                assert finding.status is DiagnosticStatus.WARNING
            else:
                assert finding.status is DiagnosticStatus.PASS
        assert report.overall_status is DiagnosticStatus.WARNING


class TestHealthCheckEngineIntegration:
    async def test_a_fully_configured_engine_is_healthy(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        config = LLMProviderConfig(
            provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("real-key")
        )
        llm_adapter = LLMAdapter(ClaudeProvider(config), config)
        repair_engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter), RepairValidator(validation_engine)
        )
        engine = HealthCheckEngine(
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            prompt_compiler=PromptCompiler(),
            llm_provider_config=config,
            sql_validation_engine=validation_engine,
            sql_repair_engine=repair_engine,
            connection_provider=connection_provider,
        )
        report = await engine.check()

        assert report.overall_status is HealthStatus.HEALTHY
        assert all(check.status is HealthStatus.HEALTHY for check in report.checks)


class TestStageInstrumentationWithARealCall:
    def test_wraps_a_real_nlu_parse_without_changing_its_result(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        parser = QueryParser()

        with StageInstrumentation(logger, "nlu"):
            query_context = parser.parse("Who are our top 10 customers by revenue?")

        assert query_context.original_question == "Who are our top 10 customers by revenue?"
        assert [r.event_type for r in sink.records] == [
            LogEventType.STARTED,
            LogEventType.COMPLETED,
        ]
        assert sink.records[1].duration_ms is not None


class TestObservabilityWithARealPipeline:
    async def test_metrics_profiler_and_benchmark_against_a_real_pipeline_run(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        query_library: QueryLibraryRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        runner = _build_pipeline_runner(
            metadata_registry, business_knowledge_registry, query_library, connection_provider
        )
        engine = QueryMindEngine(runner)
        response = await engine.ask("Who are our top 5 customers by revenue?")
        assert response.status.value == "success"

        # --- metrics: feed real PipelineStatistics into InMemoryMetricsCollector ---
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=response.status.value == "success",
            latency_ms=response.statistics.total_latency_ms,
            repair_attempted=response.statistics.repair_attempted,
            repair_succeeded=response.statistics.repair_performed,
        )
        for timing in response.statistics.stage_timings:
            collector.record_stage_latency(timing.stage.value, timing.latency_ms)
        snapshot = collector.snapshot()
        assert snapshot.pipeline_run_count == 1
        assert snapshot.pipeline_success_count == 1
        assert len(snapshot.stage_metrics) == len(response.statistics.stage_timings)

        # --- profiling: feed the same real stage timings into PipelineProfiler ---
        stage_durations = [(t.stage.value, t.latency_ms) for t in response.statistics.stage_timings]
        profile = PipelineProfiler().profile(stage_durations)
        assert profile.total_latency_ms == pytest.approx(
            sum(t.latency_ms for t in response.statistics.stage_timings)
        )
        assert profile.dominant_stage in {t.stage.value for t in response.statistics.stage_timings}

        # --- benchmarking: time the real end-to-end pipeline call itself ---
        benchmark_runner = BenchmarkRunner(warmup_iterations=0, measured_iterations=2)
        result = await benchmark_runner.run_async(
            "end_to_end_pipeline",
            lambda: engine.ask("Who are our top 5 customers by revenue?"),
        )
        assert result.measured_iterations == 2
        assert result.average_ms >= 0.0
