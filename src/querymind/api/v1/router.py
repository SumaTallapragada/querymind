"""Aggregate router for API v1.

Future phases add new endpoint modules under ``endpoints/`` and register
them here — this is the single place that defines what's exposed under
``/api/v1``.
"""

from __future__ import annotations

from fastapi import APIRouter

from querymind.api.routers import (
    diagnostics,
    execution,
    formatting,
    metrics,
    query,
    repair,
    settings,
    sql,
    validation,
)
from querymind.api.routers import (
    health as full_health,
)
from querymind.api.v1.endpoints import health
from querymind.streaming import sse

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(query.router)
api_router.include_router(sql.router)
api_router.include_router(validation.router)
api_router.include_router(repair.router)
api_router.include_router(execution.router)
api_router.include_router(formatting.router)
api_router.include_router(full_health.router)
api_router.include_router(diagnostics.router)
api_router.include_router(metrics.router)
api_router.include_router(settings.router)
# `POST /query/stream` (Phase 17) joins the rest of the `/query/*` family here, under
# `/api/v1`; `/ws/query` (`querymind.streaming.websocket`) is mounted directly on the app in
# `querymind.api.app`, unversioned, matching the spec's literal `/ws/query` path.
api_router.include_router(sse.router)
