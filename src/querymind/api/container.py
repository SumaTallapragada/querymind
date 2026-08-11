"""ApplicationContainer: constructs every engine the API layer needs, once, at startup.

The composition root's composition root: `querymind.api.lifespan` calls
`ApplicationContainer.build` exactly once per process (mirroring how
every prior phase's own `test_integration.py` assembles the real stack),
and every route reaches its engines through this one, already-built
instance via `querymind.api.dependencies` -- never by constructing an
engine, a registry, or a collaborator itself. Nothing here is global or
module-level: the container is an ordinary object, held on `app.state`,
constructor-injectable into anything that needs it (a route, a test).

`build` performs no I/O and is not `async` -- every step (loading the
metadata registry, business knowledge, and query library; constructing
every engine) is pure, in-memory construction; the only thing requiring
a live connection is the database engine itself, which
`querymind.db.engine.create_engine` builds lazily (the connection pool
opens its first real connection on first use, not at construction). This
is what keeps `Settings()` -- and therefore this container -- safe to
build against a `Settings` instance whose Postgres credentials don't
actually resolve to a reachable database (e.g. `tests/conftest.py`'s
hermetic fixture); only an endpoint that actually touches the database
(execution, health, diagnostics) would ever surface that.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

import querymind.models  # noqa: F401 -- populates Base.registry; must run before MetadataExtractor
from querymind.auth.repository import AuthenticationRepository
from querymind.auth.service import AuthenticationService
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory
from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HTTPTransport
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.models.base import Base
from querymind.nlu import QueryParser
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.health import HealthCheckEngine
from querymind.observability.logger import Logger, StructuredLogger
from querymind.observability.metrics import InMemoryMetricsCollector, MetricsCollector
from querymind.orchestrator import PipelineRunner, QueryMindEngine
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.result_formatter import ResultFormatterEngine
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker
from querymind.security.audit import AuditLogger
from querymind.security.rate_limiter import (
    InMemoryTokenBucketRateLimiter,
    NoOpRateLimiter,
    RateLimiter,
)
from querymind.security.repository import AuditRepository
from querymind.sql_execution import DatabaseConnectionProvider, SQLExecutionEngine
from querymind.sql_generation import SQLGenerationEngine
from querymind.sql_repair import SQLRepairEngine, SQLRepairLLMAdapter
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation import SQLValidationEngine
from querymind.streaming.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Every engine the API layer's routes and lifespan need, constructed exactly once."""

    settings: Settings
    engine: AsyncEngine
    metadata_registry: MetadataRegistry
    relationship_graph: RelationshipGraph
    business_knowledge_registry: BusinessKnowledgeRegistry
    query_library: QueryLibraryRegistry
    retrieval_engine: RetrievalEngine
    prompt_compiler: PromptCompiler
    llm_adapter: LLMAdapter
    sql_generation_engine: SQLGenerationEngine
    sql_validation_engine: SQLValidationEngine
    sql_repair_engine: SQLRepairEngine
    connection_provider: DatabaseConnectionProvider
    sql_execution_engine: SQLExecutionEngine
    result_formatter_engine: ResultFormatterEngine
    pipeline_runner: PipelineRunner
    query_mind_engine: QueryMindEngine
    diagnostics_engine: DiagnosticsEngine
    health_check_engine: HealthCheckEngine
    metrics_collector: MetricsCollector
    logger: Logger
    event_bus: EventBus
    authentication_repository: AuthenticationRepository
    authentication_service: AuthenticationService
    audit_repository: AuditRepository
    audit_logger: AuditLogger
    rate_limiter: RateLimiter

    @staticmethod
    def build(
        settings: Settings, *, llm_transport: HTTPTransport | None = None
    ) -> ApplicationContainer:
        """Construct every engine from `settings`. Pure construction -- see module docstring.

        `llm_transport` is `None` in production (`ClaudeProvider` then
        opens its own real `HttpxTransport`); tests pass an
        `httpx.MockTransport`-backed one so the fully-wired app never
        makes a real network call, mirroring
        `tests/orchestrator/conftest.py`'s `make_pipeline_runner(handler=...)`.
        """
        engine = create_engine(settings)

        metadata_registry = MetadataRegistry(
            MetadataExtractor(Base.registry), ColumnDictionary.default()
        )
        metadata_registry.load()
        relationship_graph = metadata_registry.build_graph()

        business_knowledge_registry = BusinessKnowledgeRegistry()
        business_knowledge_registry.load()

        query_library = QueryLibraryRegistry()
        query_library.load()

        retrieval_engine = RetrievalEngine(
            query_library=query_library, business_knowledge=business_knowledge_registry
        )
        prompt_compiler = PromptCompiler()

        llm_provider_config = settings.llm_provider_config
        llm_adapter = LLMAdapter(
            ClaudeProvider(llm_provider_config, transport=llm_transport), llm_provider_config
        )

        sql_generation_engine = SQLGenerationEngine(llm_adapter)
        sql_validation_engine = SQLValidationEngine(
            metadata_registry, business_knowledge_registry, relationship_graph
        )
        sql_repair_engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter), RepairValidator(sql_validation_engine)
        )

        connection_provider = DatabaseConnectionProvider(engine)
        sql_execution_engine = SQLExecutionEngine(connection_provider)
        result_formatter_engine = ResultFormatterEngine()

        pipeline_runner = PipelineRunner(
            nlu_parser=QueryParser(),
            schema_linker=SchemaLinker(metadata_registry),
            business_knowledge_registry=business_knowledge_registry,
            retrieval_engine=retrieval_engine,
            prompt_compiler=prompt_compiler,
            sql_generation_engine=sql_generation_engine,
            sql_validation_engine=sql_validation_engine,
            sql_repair_engine=sql_repair_engine,
            sql_execution_engine=sql_execution_engine,
            result_formatter_engine=result_formatter_engine,
        )
        query_mind_engine = QueryMindEngine(pipeline_runner)

        diagnostics_engine = DiagnosticsEngine(
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            prompt_compiler=prompt_compiler,
            llm_provider_config=llm_provider_config,
            connection_provider=connection_provider,
        )
        health_check_engine = HealthCheckEngine(
            metadata_registry=metadata_registry,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            prompt_compiler=prompt_compiler,
            llm_provider_config=llm_provider_config,
            sql_validation_engine=sql_validation_engine,
            sql_repair_engine=sql_repair_engine,
            connection_provider=connection_provider,
        )

        # Phase 22A Part 2: `AuthenticationRepository` gets its own `session_factory`, built
        # from the same `engine` (and therefore the same connection pool) as everything else in
        # this container -- not the one `querymind.api.lifespan` separately builds onto
        # `app.state.session_factory` for the pre-existing `/api/v1/health/ready` dependency,
        # since that only exists *after* this container has already been returned. Two
        # `async_sessionmaker`s over the same engine is not a real duplication of any resource
        # (a session factory is a stateless, near-free wrapper); it just avoids the layering
        # inversion of this container depending on something `lifespan` builds from it.
        authentication_session_factory = create_session_factory(engine)
        authentication_repository = AuthenticationRepository(authentication_session_factory)
        authentication_service = AuthenticationService(
            authentication_repository,
            jwt_secret_key=settings.jwt_secret_key.get_secret_value(),
            jwt_algorithm=settings.jwt_algorithm,
            access_token_expire_minutes=settings.access_token_expire_minutes,
            refresh_token_expire_days=settings.refresh_token_expire_days,
        )

        # Phase 22D: its own session factory over the same `engine`, mirroring
        # `authentication_session_factory` immediately above -- not a real duplicated resource
        # (a session factory is a stateless, near-free wrapper), just avoiding a layering
        # inversion the same way that comment already explains.
        audit_session_factory = create_session_factory(engine)
        audit_repository = AuditRepository(audit_session_factory)
        audit_logger = AuditLogger(audit_repository)

        # `NoOpRateLimiter` when disabled, not a conditional inside every dependency that uses
        # it -- see `querymind.security.rate_limiter`'s own docstring: both implementations
        # share one call shape, so every rate-limit dependency in `querymind.api.dependencies`
        # calls `.check(...)` unconditionally regardless of which one this process is running.
        rate_limiter: RateLimiter = (
            InMemoryTokenBucketRateLimiter() if settings.rate_limit_enabled else NoOpRateLimiter()
        )

        return ApplicationContainer(
            settings=settings,
            engine=engine,
            metadata_registry=metadata_registry,
            relationship_graph=relationship_graph,
            business_knowledge_registry=business_knowledge_registry,
            query_library=query_library,
            retrieval_engine=retrieval_engine,
            prompt_compiler=prompt_compiler,
            llm_adapter=llm_adapter,
            sql_generation_engine=sql_generation_engine,
            sql_validation_engine=sql_validation_engine,
            sql_repair_engine=sql_repair_engine,
            connection_provider=connection_provider,
            sql_execution_engine=sql_execution_engine,
            result_formatter_engine=result_formatter_engine,
            pipeline_runner=pipeline_runner,
            query_mind_engine=query_mind_engine,
            diagnostics_engine=diagnostics_engine,
            health_check_engine=health_check_engine,
            metrics_collector=InMemoryMetricsCollector(),
            logger=StructuredLogger(),
            event_bus=EventBus(),
            authentication_repository=authentication_repository,
            authentication_service=authentication_service,
            audit_repository=audit_repository,
            audit_logger=audit_logger,
            rate_limiter=rate_limiter,
        )

    async def dispose(self) -> None:
        """Release everything with a real resource to release -- just the database engine today."""
        await self.engine.dispose()
