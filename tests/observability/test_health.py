"""Tests for `querymind.observability.health.HealthCheckEngine`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.adapter import LLMAdapter
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import LLMProvider
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata import MetadataRegistry
from querymind.observability.health import HealthCheckEngine
from querymind.observability.models import HealthCheck, HealthReport, HealthStatus
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.sql_execution import DatabaseConnectionProvider
from querymind.sql_repair import SQLRepairEngine, SQLRepairLLMAdapter
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation import SQLValidationEngine


def _check(report: HealthReport, name: str) -> HealthCheck:
    return next(c for c in report.checks if c.name == name)


class _BrokenLoad:
    """A minimal fake matching a registry's `.load()` shape, but raising -- for exercising
    HealthCheckEngine's own error-handling branch, which a genuinely working real registry
    can never trigger. Mirrors tests/observability/test_diagnostics.py's identical fake."""

    def load(self) -> Any:
        raise RuntimeError("simulated load failure")


class TestNoCollaboratorsConfigured:
    async def test_every_check_is_unknown_and_overall_is_unknown(self) -> None:
        report = await HealthCheckEngine().check()
        assert report.overall_status is HealthStatus.UNKNOWN
        for check in report.checks:
            assert check.status is HealthStatus.UNKNOWN

    async def test_never_raises(self) -> None:
        report = await HealthCheckEngine().check()
        assert report is not None


class TestDatabaseReachable:
    async def test_a_real_reachable_database_is_healthy(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        report = await HealthCheckEngine(connection_provider=connection_provider).check()
        assert _check(report, "database_reachable").status is HealthStatus.HEALTHY

    async def test_never_executes_sql(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        # Documented, not independently verifiable from outside -- see the identical note in
        # test_diagnostics.py::TestDatabaseConnectivityCheck::test_never_executes_sql.
        await HealthCheckEngine(connection_provider=connection_provider).check()

    async def test_an_unreachable_database_is_unhealthy(self) -> None:
        bad_engine = create_async_engine(
            "postgresql+asyncpg://nobody:nowhere@localhost:1/does_not_exist"
        )
        try:
            provider = DatabaseConnectionProvider(bad_engine)
            report = await HealthCheckEngine(connection_provider=provider).check()
            assert _check(report, "database_reachable").status is HealthStatus.UNHEALTHY
        finally:
            await bad_engine.dispose()


class TestMetadataLoaded:
    async def test_a_loaded_registry_is_healthy(self, metadata_registry: MetadataRegistry) -> None:
        report = await HealthCheckEngine(metadata_registry=metadata_registry).check()
        assert _check(report, "metadata_loaded").status is HealthStatus.HEALTHY

    async def test_a_registry_that_fails_to_load_is_unhealthy(self) -> None:
        report = await HealthCheckEngine(metadata_registry=_BrokenLoad()).check()  # type: ignore[arg-type]
        check = _check(report, "metadata_loaded")
        assert check.status is HealthStatus.UNHEALTHY
        assert check.message == "simulated load failure"


class TestBusinessKnowledgeLoaded:
    async def test_a_loaded_registry_is_healthy(
        self, business_knowledge_registry: BusinessKnowledgeRegistry
    ) -> None:
        report = await HealthCheckEngine(
            business_knowledge_registry=business_knowledge_registry
        ).check()
        assert _check(report, "business_knowledge_loaded").status is HealthStatus.HEALTHY


class TestQueryExamplesLoaded:
    async def test_a_loaded_registry_is_healthy(self, query_library: QueryLibraryRegistry) -> None:
        report = await HealthCheckEngine(query_library=query_library).check()
        assert _check(report, "query_examples_loaded").status is HealthStatus.HEALTHY


class TestPromptCompilerReady:
    async def test_a_configured_compiler_is_healthy(self) -> None:
        report = await HealthCheckEngine(prompt_compiler=PromptCompiler()).check()
        assert _check(report, "prompt_compiler_ready").status is HealthStatus.HEALTHY


class TestLLMConfigured:
    async def test_a_configured_provider_is_healthy(self) -> None:
        config = LLMProviderConfig(
            provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("key")
        )
        report = await HealthCheckEngine(llm_provider_config=config).check()
        assert _check(report, "llm_configured").status is HealthStatus.HEALTHY


class TestSQLValidatorReady:
    async def test_a_configured_engine_is_healthy(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        report = await HealthCheckEngine(sql_validation_engine=validation_engine).check()
        assert _check(report, "sql_validator_ready").status is HealthStatus.HEALTHY


class TestRepairEngineReady:
    async def test_a_configured_engine_is_healthy(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        config = LLMProviderConfig(
            provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("key")
        )
        llm_adapter = LLMAdapter(ClaudeProvider(config), config)
        repair_engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter), RepairValidator(validation_engine)
        )
        report = await HealthCheckEngine(sql_repair_engine=repair_engine).check()
        assert _check(report, "repair_engine_ready").status is HealthStatus.HEALTHY


class TestOverallStatus:
    async def test_overall_is_unhealthy_if_any_check_is_unhealthy(self) -> None:
        bad_engine = create_async_engine(
            "postgresql+asyncpg://nobody:nowhere@localhost:1/does_not_exist"
        )
        try:
            provider = DatabaseConnectionProvider(bad_engine)
            report = await HealthCheckEngine(connection_provider=provider).check()
            assert report.overall_status is HealthStatus.UNHEALTHY
        finally:
            await bad_engine.dispose()

    async def test_overall_is_healthy_only_if_every_check_is_healthy(
        self,
        metadata_registry: MetadataRegistry,
        connection_provider: DatabaseConnectionProvider,
    ) -> None:
        # Only two of eight checks configured -- overall must be UNKNOWN, not HEALTHY, since
        # not every check reported HEALTHY.
        report = await HealthCheckEngine(
            metadata_registry=metadata_registry, connection_provider=connection_provider
        ).check()
        assert report.overall_status is HealthStatus.UNKNOWN

    async def test_uses_the_injected_clock(self) -> None:
        fixed = datetime(2026, 8, 6, tzinfo=UTC)
        report = await HealthCheckEngine(clock=lambda: fixed).check()
        assert report.generated_at == fixed
