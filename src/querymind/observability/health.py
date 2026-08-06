"""HealthCheckEngine: lightweight, binary readiness checks. Never executes SQL.

Distinct from `DiagnosticsEngine` (`diagnostics.py`) in shape and intent:
diagnostics answers "what, in detail, is wrong or noteworthy," with a
three-level status and a human-readable message per check; health answers
the narrower, operational question "is each of these components ready to
serve traffic," with a two-level (`HEALTHY`/`UNHEALTHY`, plus `UNKNOWN`
for "not configured") status suited to a liveness/readiness-style probe.
Both exist because they serve different operators at different times --
diagnostics for someone debugging a problem, health for an automated
check run on a schedule.

Every collaborator is optional and every check is read-only, exactly like
`DiagnosticsEngine` -- see that module's docstring for the same reasoning
about "never raises" and "never executes SQL, only opens/closes a
connection."
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.llm.config import LLMProviderConfig
from querymind.metadata import MetadataRegistry
from querymind.observability.models import HealthCheck, HealthReport, HealthStatus
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.sql_execution import DatabaseConnectionProvider
from querymind.sql_repair import SQLRepairEngine
from querymind.sql_validation import SQLValidationEngine


class HealthCheckEngine:
    """Reports HEALTHY/UNHEALTHY/UNKNOWN for each configured collaborator. Never raises."""

    def __init__(
        self,
        metadata_registry: MetadataRegistry | None = None,
        business_knowledge_registry: BusinessKnowledgeRegistry | None = None,
        query_library: QueryLibraryRegistry | None = None,
        prompt_compiler: PromptCompiler | None = None,
        llm_provider_config: LLMProviderConfig | None = None,
        sql_validation_engine: SQLValidationEngine | None = None,
        sql_repair_engine: SQLRepairEngine | None = None,
        connection_provider: DatabaseConnectionProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._metadata_registry = metadata_registry
        self._business_knowledge_registry = business_knowledge_registry
        self._query_library = query_library
        self._prompt_compiler = prompt_compiler
        self._llm_provider_config = llm_provider_config
        self._sql_validation_engine = sql_validation_engine
        self._sql_repair_engine = sql_repair_engine
        self._connection_provider = connection_provider
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    async def check(self) -> HealthReport:
        """Run every check and return a complete `HealthReport`. Never raises."""
        checks = [
            await self._check_database_reachable(),
            self._check_loaded("metadata_loaded", self._metadata_registry),
            self._check_loaded("business_knowledge_loaded", self._business_knowledge_registry),
            self._check_loaded("query_examples_loaded", self._query_library),
            self._check_present("prompt_compiler_ready", self._prompt_compiler),
            self._check_present("llm_configured", self._llm_provider_config),
            self._check_present("sql_validator_ready", self._sql_validation_engine),
            self._check_present("repair_engine_ready", self._sql_repair_engine),
        ]
        overall = self._overall_status(checks)
        return HealthReport(
            checks=tuple(checks), overall_status=overall, generated_at=self._clock()
        )

    @staticmethod
    def _overall_status(checks: list[HealthCheck]) -> HealthStatus:
        statuses = {check.status for check in checks}
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if statuses == {HealthStatus.HEALTHY}:
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN

    @staticmethod
    def _check_present(name: str, collaborator: object | None) -> HealthCheck:
        if collaborator is None:
            return HealthCheck(name=name, status=HealthStatus.UNKNOWN, message="Not configured.")
        return HealthCheck(name=name, status=HealthStatus.HEALTHY)

    @staticmethod
    def _check_loaded(
        name: str,
        registry: MetadataRegistry | BusinessKnowledgeRegistry | QueryLibraryRegistry | None,
    ) -> HealthCheck:
        if registry is None:
            return HealthCheck(name=name, status=HealthStatus.UNKNOWN, message="Not configured.")
        try:
            registry.load()
        except Exception as exc:  # a registry that fails to load is genuinely unhealthy
            return HealthCheck(name=name, status=HealthStatus.UNHEALTHY, message=str(exc))
        return HealthCheck(name=name, status=HealthStatus.HEALTHY)

    async def _check_database_reachable(self) -> HealthCheck:
        if self._connection_provider is None:
            return HealthCheck(
                name="database_reachable", status=HealthStatus.UNKNOWN, message="Not configured."
            )
        try:
            async with self._connection_provider.acquire():
                pass  # Connectivity only -- never execute anything through this connection.
        except Exception as exc:
            return HealthCheck(
                name="database_reachable", status=HealthStatus.UNHEALTHY, message=str(exc)
            )
        return HealthCheck(name="database_reachable", status=HealthStatus.HEALTHY)
