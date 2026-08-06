"""Liveness and readiness probes.

Split into two endpoints on purpose — they answer different questions and
are consumed by different parts of a container orchestrator:

* ``/health/live``  — "is this process alive?" No dependencies are checked.
  Used to decide whether to *restart* the container.
* ``/health/ready`` — "can this process serve traffic right now?" Checks
  the database is reachable. Used to decide whether to *route* traffic to
  it. Coupling liveness to the database would cause a healthy process to
  be killed and restarted during a transient database blip, which does
  nothing to fix the outage and adds churn on top of it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from querymind.api.dependencies import DbSessionDep

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"]


class ReadinessStatus(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


@router.get("/live", response_model=HealthStatus, status_code=status.HTTP_200_OK)
async def liveness() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready", response_model=ReadinessStatus, status_code=status.HTTP_200_OK)
async def readiness(session: DbSessionDep) -> ReadinessStatus:
    await session.execute(text("SELECT 1"))
    return ReadinessStatus(status="ok", database="ok")
