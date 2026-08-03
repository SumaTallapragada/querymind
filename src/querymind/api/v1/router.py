"""Aggregate router for API v1.

Future phases add new endpoint modules under ``endpoints/`` and register
them here — this is the single place that defines what's exposed under
``/api/v1``.
"""

from __future__ import annotations

from fastapi import APIRouter

from querymind.api.v1.endpoints import health

api_router = APIRouter()
api_router.include_router(health.router)
