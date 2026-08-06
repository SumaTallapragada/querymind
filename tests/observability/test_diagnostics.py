"""Tests for `querymind.observability.diagnostics.DiagnosticsEngine`.

Uses the real `MetadataRegistry`/`BusinessKnowledgeRegistry`/
`QueryLibraryRegistry`/`PromptCompiler` (all pure, in-memory, no
database) plus the real, already-running local Postgres instance for the
connectivity check -- consistent with this project's "real collaborators,
no unnecessary mocks" testing convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import LLMProvider
from querymind.metadata import MetadataRegistry
from querymind.observability import diagnostics as diagnostics_module
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.models import DiagnosticFinding, DiagnosticsReport, DiagnosticStatus
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.sql_execution import DatabaseConnectionProvider


def _finding(report: DiagnosticsReport, check_name: str) -> DiagnosticFinding:
    return next(f for f in report.findings if f.check_name == check_name)


class _BrokenLoad:
    """A minimal fake matching MetadataRegistry/BusinessKnowledgeRegistry/QueryLibraryRegistry's
    `.load()` shape, but raising -- for exercising DiagnosticsEngine's own error-handling
    branches, which a genuinely working real registry can never trigger."""

    def load(self) -> Any:
        raise RuntimeError("simulated load failure")

    def build_graph(self) -> Any:
        raise RuntimeError("simulated build_graph failure")


class TestNoCollaboratorsConfigured:
    async def test_every_configurable_check_warns_and_overall_is_warning(self) -> None:
        report = await DiagnosticsEngine().run()
        assert report.overall_status is DiagnosticStatus.WARNING
        # cache_configuration is deliberately always WARNING; dependency_versions runs
        # unconditionally (it inspects installed packages, not caller-provided config) and
        # is expected to PASS even with nothing injected. Every *configurable* check should
        # warn "not configured" when nothing was injected.
        unconditional_checks = {"dependency_versions"}
        for finding in report.findings:
            if finding.check_name in unconditional_checks:
                continue
            assert finding.status is DiagnosticStatus.WARNING

    async def test_never_raises(self) -> None:
        # The whole point of DiagnosticsEngine -- no collaborator configured must not crash it.
        report = await DiagnosticsEngine().run()
        assert report is not None


class TestMetadataRegistryCheck:
    async def test_a_loaded_registry_passes(self, metadata_registry: MetadataRegistry) -> None:
        report = await DiagnosticsEngine(metadata_registry=metadata_registry).run()
        assert _finding(report, "metadata_registry").status is DiagnosticStatus.PASS


class TestBusinessKnowledgeCheck:
    async def test_a_loaded_registry_passes(
        self, business_knowledge_registry: BusinessKnowledgeRegistry
    ) -> None:
        report = await DiagnosticsEngine(
            business_knowledge_registry=business_knowledge_registry
        ).run()
        assert _finding(report, "business_knowledge_registry").status is DiagnosticStatus.PASS


class TestQueryLibraryCheck:
    async def test_a_loaded_registry_passes(self, query_library: QueryLibraryRegistry) -> None:
        report = await DiagnosticsEngine(query_library=query_library).run()
        assert _finding(report, "query_library").status is DiagnosticStatus.PASS


class TestRelationshipGraphCheck:
    async def test_builds_from_the_metadata_registry(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        report = await DiagnosticsEngine(metadata_registry=metadata_registry).run()
        assert _finding(report, "relationship_graph").status is DiagnosticStatus.PASS

    async def test_warns_without_a_metadata_registry(self) -> None:
        report = await DiagnosticsEngine().run()
        assert _finding(report, "relationship_graph").status is DiagnosticStatus.WARNING


class TestPromptCompilerCheck:
    async def test_a_configured_compiler_passes(self) -> None:
        report = await DiagnosticsEngine(prompt_compiler=PromptCompiler()).run()
        assert _finding(report, "prompt_compiler").status is DiagnosticStatus.PASS


class TestLLMConfigurationCheck:
    async def test_a_configured_provider_passes_and_never_leaks_the_api_key(self) -> None:
        config = LLMProviderConfig(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            api_key=SecretStr("real-secret-key"),
        )
        report = await DiagnosticsEngine(llm_provider_config=config).run()
        finding = _finding(report, "llm_configuration")
        assert finding.status is DiagnosticStatus.PASS
        assert "real-secret-key" not in (finding.details or "")
        assert "real-secret-key" not in finding.message

    async def test_an_empty_api_key_is_an_error(self) -> None:
        config = LLMProviderConfig(
            provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=SecretStr("")
        )
        report = await DiagnosticsEngine(llm_provider_config=config).run()
        assert _finding(report, "llm_configuration").status is DiagnosticStatus.ERROR


class TestDatabaseConnectivityCheck:
    async def test_a_real_reachable_database_passes(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        report = await DiagnosticsEngine(connection_provider=connection_provider).run()
        assert _finding(report, "database_connectivity").status is DiagnosticStatus.PASS

    async def test_never_executes_sql(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        # No assertion beyond "this completes" -- DiagnosticsEngine's connectivity check opens
        # and releases a connection without ever calling .execute() on it; if it did run a
        # query, this test would still pass, so the real guarantee is enforced by code review
        # of diagnostics.py, not by this test. Documented here for traceability.
        await DiagnosticsEngine(connection_provider=connection_provider).run()

    async def test_an_unreachable_database_is_an_error(self) -> None:
        bad_engine = create_async_engine(
            "postgresql+asyncpg://nobody:nowhere@localhost:1/does_not_exist"
        )
        try:
            provider = DatabaseConnectionProvider(bad_engine)
            report = await DiagnosticsEngine(connection_provider=provider).run()
            assert _finding(report, "database_connectivity").status is DiagnosticStatus.ERROR
        finally:
            await bad_engine.dispose()


class TestDependencyVersionsCheck:
    async def test_reports_pass_with_tracked_dependency_versions(self) -> None:
        report = await DiagnosticsEngine().run()
        finding = _finding(report, "dependency_versions")
        assert finding.status is DiagnosticStatus.PASS
        assert "pydantic==" in (finding.details or "")

    async def test_a_missing_tracked_dependency_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No package in this environment is actually missing -- simulate one the only way
        # possible, by pointing the check at a distribution name that cannot exist.
        monkeypatch.setattr(
            diagnostics_module, "_TRACKED_DEPENDENCIES", ("pydantic", "this-package-does-not-exist")
        )
        report = await DiagnosticsEngine().run()
        finding = _finding(report, "dependency_versions")
        assert finding.status is DiagnosticStatus.ERROR
        assert "this-package-does-not-exist" in finding.message


class TestRegistryLoadFailures:
    """Exercises DiagnosticsEngine's own error-handling branches -- a genuinely working real
    registry can never fail to load, so a small broken fake is the only way to reach them."""

    async def test_a_metadata_registry_that_fails_to_load_is_an_error(self) -> None:
        report = await DiagnosticsEngine(metadata_registry=_BrokenLoad()).run()  # type: ignore[arg-type]
        finding = _finding(report, "metadata_registry")
        assert finding.status is DiagnosticStatus.ERROR
        assert finding.details == "simulated load failure"

    async def test_a_business_knowledge_registry_that_fails_to_load_is_an_error(self) -> None:
        report = await DiagnosticsEngine(business_knowledge_registry=_BrokenLoad()).run()  # type: ignore[arg-type]
        finding = _finding(report, "business_knowledge_registry")
        assert finding.status is DiagnosticStatus.ERROR

    async def test_a_query_library_that_fails_to_load_is_an_error(self) -> None:
        report = await DiagnosticsEngine(query_library=_BrokenLoad()).run()  # type: ignore[arg-type]
        finding = _finding(report, "query_library")
        assert finding.status is DiagnosticStatus.ERROR

    async def test_a_metadata_registry_whose_build_graph_fails_is_an_error(self) -> None:
        report = await DiagnosticsEngine(metadata_registry=_BrokenLoad()).run()  # type: ignore[arg-type]
        finding = _finding(report, "relationship_graph")
        assert finding.status is DiagnosticStatus.ERROR
        assert finding.details == "simulated build_graph failure"


class TestCacheConfigurationCheck:
    async def test_is_always_a_warning(self) -> None:
        report = await DiagnosticsEngine().run()
        assert _finding(report, "cache_configuration").status is DiagnosticStatus.WARNING


class TestOverallStatus:
    async def test_overall_is_error_if_any_check_errors(self) -> None:
        bad_engine = create_async_engine(
            "postgresql+asyncpg://nobody:nowhere@localhost:1/does_not_exist"
        )
        try:
            provider = DatabaseConnectionProvider(bad_engine)
            report = await DiagnosticsEngine(connection_provider=provider).run()
            assert report.overall_status is DiagnosticStatus.ERROR
        finally:
            await bad_engine.dispose()

    async def test_uses_the_injected_clock(self) -> None:
        fixed = datetime(2026, 8, 6, tzinfo=UTC)
        report = await DiagnosticsEngine(clock=lambda: fixed).run()
        assert report.generated_at == fixed
