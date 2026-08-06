"""DiagnosticsEngine: read-only, non-raising inspection of the pipeline's own configuration.

Every check inspects an already-constructed collaborator (a registry, a
config object, a connection provider) via its own public API only --
never another phase's internal implementation -- and never modifies
anything. `run()` never raises: a collaborator that is missing,
misconfigured, or unreachable becomes a `WARNING`/`ERROR`
`DiagnosticFinding`, not an exception, so a caller can always get a
complete report even when several things are wrong at once.

Every collaborator is optional (`X | None = None`) -- `DiagnosticsEngine`
is meant to be usable with whatever subset of the pipeline a caller has
actually wired up (e.g. just the metadata layer, with no LLM configured
yet), not only against a fully assembled `PipelineRunner`.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from datetime import UTC, datetime

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.config import LLMProviderConfig
from querymind.metadata import MetadataRegistry
from querymind.observability.models import DiagnosticFinding, DiagnosticsReport, DiagnosticStatus
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.sql_execution import DatabaseConnectionProvider

#: Worst-status-wins ordering used to compute DiagnosticsReport.overall_status.
_STATUS_SEVERITY: dict[DiagnosticStatus, int] = {
    DiagnosticStatus.PASS: 0,
    DiagnosticStatus.WARNING: 1,
    DiagnosticStatus.ERROR: 2,
}

#: Dependency distributions worth reporting installed versions for -- the ones this
#: project's own architecture depends on most directly (see ARCHITECTURE.md).
_TRACKED_DEPENDENCIES: tuple[str, ...] = (
    "pydantic",
    "sqlalchemy",
    "sqlglot",
    "httpx",
    "fastapi",
)


class DiagnosticsEngine:
    """Inspects the pipeline's own configuration and reports PASS/WARNING/ERROR per check.

    Never executes SQL -- the database connectivity check opens and
    immediately releases a connection via `DatabaseConnectionProvider`,
    without ever calling `.execute()` on it.
    """

    def __init__(
        self,
        metadata_registry: MetadataRegistry | None = None,
        business_knowledge_registry: BusinessKnowledgeRegistry | None = None,
        query_library: QueryLibraryRegistry | None = None,
        prompt_compiler: PromptCompiler | None = None,
        llm_provider_config: LLMProviderConfig | None = None,
        connection_provider: DatabaseConnectionProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._metadata_registry = metadata_registry
        self._business_knowledge_registry = business_knowledge_registry
        self._query_library = query_library
        self._prompt_compiler = prompt_compiler
        self._llm_provider_config = llm_provider_config
        self._connection_provider = connection_provider
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    async def run(self) -> DiagnosticsReport:
        """Run every check and return a complete `DiagnosticsReport`. Never raises."""
        findings = [
            self._check_metadata_registry(),
            self._check_business_knowledge(),
            self._check_query_library(),
            self._check_relationship_graph(),
            self._check_prompt_compiler(),
            self._check_llm_configuration(),
            await self._check_database_connectivity(),
            self._check_dependency_versions(),
            self._check_cache_configuration(),
        ]
        overall = max(findings, key=lambda f: _STATUS_SEVERITY[f.status]).status
        return DiagnosticsReport(
            findings=tuple(findings), overall_status=overall, generated_at=self._clock()
        )

    def _check_metadata_registry(self) -> DiagnosticFinding:
        if self._metadata_registry is None:
            return DiagnosticFinding(
                check_name="metadata_registry",
                status=DiagnosticStatus.WARNING,
                message="No MetadataRegistry configured.",
            )
        try:
            metadata = self._metadata_registry.load()
        except Exception as exc:  # diagnostics must never raise, see class docstring
            return DiagnosticFinding(
                check_name="metadata_registry",
                status=DiagnosticStatus.ERROR,
                message="MetadataRegistry.load() failed.",
                details=str(exc),
            )
        if not metadata.tables:
            return DiagnosticFinding(
                check_name="metadata_registry",
                status=DiagnosticStatus.WARNING,
                message="MetadataRegistry loaded but contains no tables.",
            )
        return DiagnosticFinding(
            check_name="metadata_registry",
            status=DiagnosticStatus.PASS,
            message=f"{len(metadata.tables)} table(s) loaded.",
        )

    def _check_business_knowledge(self) -> DiagnosticFinding:
        if self._business_knowledge_registry is None:
            return DiagnosticFinding(
                check_name="business_knowledge_registry",
                status=DiagnosticStatus.WARNING,
                message="No BusinessKnowledgeRegistry configured.",
            )
        try:
            catalog = self._business_knowledge_registry.load()
        except Exception as exc:
            return DiagnosticFinding(
                check_name="business_knowledge_registry",
                status=DiagnosticStatus.ERROR,
                message="BusinessKnowledgeRegistry.load() failed.",
                details=str(exc),
            )
        return DiagnosticFinding(
            check_name="business_knowledge_registry",
            status=DiagnosticStatus.PASS,
            message=f"{len(catalog.concepts)} business concept(s) loaded.",
        )

    def _check_query_library(self) -> DiagnosticFinding:
        if self._query_library is None:
            return DiagnosticFinding(
                check_name="query_library",
                status=DiagnosticStatus.WARNING,
                message="No QueryLibraryRegistry configured.",
            )
        try:
            library = self._query_library.load()
        except Exception as exc:
            return DiagnosticFinding(
                check_name="query_library",
                status=DiagnosticStatus.ERROR,
                message="QueryLibraryRegistry.load() failed.",
                details=str(exc),
            )
        return DiagnosticFinding(
            check_name="query_library",
            status=DiagnosticStatus.PASS,
            message=f"{len(library.examples)} example(s) loaded.",
        )

    def _check_relationship_graph(self) -> DiagnosticFinding:
        if self._metadata_registry is None:
            return DiagnosticFinding(
                check_name="relationship_graph",
                status=DiagnosticStatus.WARNING,
                message="No MetadataRegistry configured; cannot build a RelationshipGraph.",
            )
        try:
            graph = self._metadata_registry.build_graph()
        except Exception as exc:
            return DiagnosticFinding(
                check_name="relationship_graph",
                status=DiagnosticStatus.ERROR,
                message="MetadataRegistry.build_graph() failed.",
                details=str(exc),
            )
        return DiagnosticFinding(
            check_name="relationship_graph",
            status=DiagnosticStatus.PASS,
            message=f"{len(graph.nodes)} node(s) in the relationship graph.",
        )

    def _check_prompt_compiler(self) -> DiagnosticFinding:
        if self._prompt_compiler is None:
            return DiagnosticFinding(
                check_name="prompt_compiler",
                status=DiagnosticStatus.WARNING,
                message="No PromptCompiler configured.",
            )
        return DiagnosticFinding(
            check_name="prompt_compiler",
            status=DiagnosticStatus.PASS,
            message="PromptCompiler ready.",
        )

    def _check_llm_configuration(self) -> DiagnosticFinding:
        if self._llm_provider_config is None:
            return DiagnosticFinding(
                check_name="llm_configuration",
                status=DiagnosticStatus.WARNING,
                message="No LLMProviderConfig configured.",
            )
        config = self._llm_provider_config
        if not config.api_key.get_secret_value():
            return DiagnosticFinding(
                check_name="llm_configuration",
                status=DiagnosticStatus.ERROR,
                message="LLMProviderConfig has an empty api_key.",
            )
        return DiagnosticFinding(
            check_name="llm_configuration",
            status=DiagnosticStatus.PASS,
            message="LLM provider configured.",
            details=f"provider={config.provider.value} model={config.model}",
        )

    async def _check_database_connectivity(self) -> DiagnosticFinding:
        if self._connection_provider is None:
            return DiagnosticFinding(
                check_name="database_connectivity",
                status=DiagnosticStatus.WARNING,
                message="No DatabaseConnectionProvider configured.",
            )
        try:
            async with self._connection_provider.acquire():
                pass  # Connectivity only -- never execute anything through this connection.
        except Exception as exc:
            return DiagnosticFinding(
                check_name="database_connectivity",
                status=DiagnosticStatus.ERROR,
                message="Could not acquire a database connection.",
                details=str(exc),
            )
        return DiagnosticFinding(
            check_name="database_connectivity",
            status=DiagnosticStatus.PASS,
            message="Database connection acquired successfully.",
        )

    @staticmethod
    def _check_dependency_versions() -> DiagnosticFinding:
        versions = []
        missing = []
        for package in _TRACKED_DEPENDENCIES:
            try:
                versions.append(f"{package}=={importlib.metadata.version(package)}")
            except importlib.metadata.PackageNotFoundError:
                missing.append(package)
        if missing:
            return DiagnosticFinding(
                check_name="dependency_versions",
                status=DiagnosticStatus.ERROR,
                message=f"Missing expected package(s): {', '.join(missing)}.",
                details=", ".join(versions) or None,
            )
        return DiagnosticFinding(
            check_name="dependency_versions",
            status=DiagnosticStatus.PASS,
            message=f"{len(versions)} tracked dependency(ies) present.",
            details=", ".join(versions),
        )

    @staticmethod
    def _check_cache_configuration() -> DiagnosticFinding:
        return DiagnosticFinding(
            check_name="cache_configuration",
            status=DiagnosticStatus.WARNING,
            message="No cache is actually active for any phase.",
            details=(
                "Every phase from prompt_compiler onward defines a Cache Protocol and a "
                "NoOp implementation; none of the real engines currently accept or call a "
                "real cache instance. See docs/KNOWN_LIMITATIONS.md."
            ),
        )
