"""Application composition root -- a thin re-export of `querymind.api.app.create_app`.

Kept as the process entry point (`uvicorn querymind.main:app`) for
backward compatibility; the actual wiring (lifespan, middleware, routers,
exception handlers) lives in `querymind.api.app`, `querymind.api.lifespan`,
`querymind.api.middleware`, and `querymind.api.exception_handlers` as of
Phase 16.
"""

from __future__ import annotations

from querymind.api.app import create_app

app = create_app()
