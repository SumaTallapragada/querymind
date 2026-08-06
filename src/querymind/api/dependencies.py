"""Shared FastAPI dependencies.

Every dependency callable here does exactly one thing: read something
already constructed (`Settings`, the `ApplicationContainer`, one engine
off it) and hand it to a route via `Depends(...)`. No dependency
constructs an engine itself -- `ApplicationContainer.build` (called once,
in `querymind.api.lifespan`) already did that; this module only resolves
references to what already exists.

`get_db_session`/`DbSessionDep` are unchanged from Phase 1 (moved here
from the now-removed `api/deps.py`, not rewritten) and back the existing
`/api/v1/health/ready` endpoint, which predates this phase and is left
exactly as it was.

`get_container` takes an `HTTPConnection`, not a `Request` -- Starlette's
common base class for both `Request` (HTTP) and `WebSocket` -- because
`querymind.streaming.websocket`'s `/ws/query` (Phase 17) resolves
`QueryMindEngineDep`/`EventBusDep`/`LoggerDep` too, and FastAPI only
auto-injects a concrete `Request` for HTTP routes / a concrete
`WebSocket` for WebSocket routes, never either for the other. Every
dependency built on top of `ContainerDep` therefore already works for
both transports with no changes of its own.

`SettingsDep` reads `container.settings`, *not*
`querymind.core.config.get_settings()` (the `lru_cache`d process-wide
singleton `create_app` falls back to when no explicit `Settings` is
given) -- the two can genuinely differ: a test builds its own `Settings`
instance and passes it to `create_app(settings=...)` explicitly, but the
very first call to `get_settings()` anywhere in the process (by any
test, in any order) permanently caches *that* call's result for the rest
of the process. A route depending on `get_settings` directly would
silently see whichever `Settings` happened to be constructed first,
never necessarily the one its own app was actually built from -- found
via `GET /settings` (Phase 18) returning the real `.env`'s database name
instead of a test's hermetic one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from querymind.api.container import ApplicationContainer
from querymind.core.config import Settings
from querymind.db.session import transactional_session
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.health import HealthCheckEngine
from querymind.observability.logger import Logger
from querymind.observability.metrics import MetricsCollector
from querymind.orchestrator import QueryMindEngine
from querymind.result_formatter import ResultFormatterEngine
from querymind.sql_execution import SQLExecutionEngine
from querymind.sql_validation import SQLValidationEngine
from querymind.streaming.event_bus import EventBus


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped async DB session for the current request.

    The session factory is read off ``app.state`` (populated once at
    startup in ``querymind.api.lifespan``) rather than constructed here,
    so the engine's connection pool is created exactly once per process
    and shared across all requests.
    """
    session_factory = request.app.state.session_factory
    async with transactional_session(session_factory) as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_container(conn: HTTPConnection) -> ApplicationContainer:
    """Return the one `ApplicationContainer` built at startup, off `app.state`."""
    container: ApplicationContainer = conn.app.state.container
    return container


ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_query_mind_engine(container: ContainerDep) -> QueryMindEngine:
    return container.query_mind_engine


def get_sql_validation_engine(container: ContainerDep) -> SQLValidationEngine:
    return container.sql_validation_engine


def get_sql_execution_engine(container: ContainerDep) -> SQLExecutionEngine:
    return container.sql_execution_engine


def get_result_formatter_engine(container: ContainerDep) -> ResultFormatterEngine:
    return container.result_formatter_engine


def get_health_check_engine(container: ContainerDep) -> HealthCheckEngine:
    return container.health_check_engine


def get_diagnostics_engine(container: ContainerDep) -> DiagnosticsEngine:
    return container.diagnostics_engine


def get_metrics_collector(container: ContainerDep) -> MetricsCollector:
    return container.metrics_collector


def get_logger(container: ContainerDep) -> Logger:
    return container.logger


def get_event_bus(container: ContainerDep) -> EventBus:
    return container.event_bus


QueryMindEngineDep = Annotated[QueryMindEngine, Depends(get_query_mind_engine)]
SQLValidationEngineDep = Annotated[SQLValidationEngine, Depends(get_sql_validation_engine)]
SQLExecutionEngineDep = Annotated[SQLExecutionEngine, Depends(get_sql_execution_engine)]
ResultFormatterEngineDep = Annotated[ResultFormatterEngine, Depends(get_result_formatter_engine)]
HealthCheckEngineDep = Annotated[HealthCheckEngine, Depends(get_health_check_engine)]
DiagnosticsEngineDep = Annotated[DiagnosticsEngine, Depends(get_diagnostics_engine)]
MetricsCollectorDep = Annotated[MetricsCollector, Depends(get_metrics_collector)]
LoggerDep = Annotated[Logger, Depends(get_logger)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
