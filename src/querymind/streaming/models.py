"""Immutable data models for the Streaming presentation layer.

Every event that ever crosses an SSE/WebSocket connection is a
`PipelineEvent` (or one of its nine subclasses below) -- there is no
second, transport-specific event shape; `querymind.streaming.serializer`
turns exactly this model into wire bytes for both transports. Every
subclass fixes `event_type` to one `PipelineEventType` value and adds
nothing to `PipelineEvent`'s own fields: type-specific data lives in
`payload`, so every event -- regardless of which subclass produced it --
serializes to the same six-key JSON shape a client can always parse
without a discriminated-union decoder.

`payload` deliberately holds already-JSON-safe primitives (built via
`.model_dump(mode="json")` on whatever real pipeline model it carries,
e.g. a `BusinessAnswer`) -- these events never invent a second
representation of a value some other phase's own model already owns;
see rule 1 of the Phase 17 spec ("streaming is presentation only").

Every model is frozen (`model_config = ConfigDict(frozen=True,
extra="forbid")`) and uses `tuple`, never `list`, for collections --
matching every other package's `models.py` in this project.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from querymind.orchestrator.models import PipelineStage, QueryMindResponse


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PipelineEventType(str, Enum):
    """Every kind of event a streamed pipeline run can emit, in no particular order."""

    PIPELINE_STARTED = "pipeline_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    HEARTBEAT = "heartbeat"
    CLIENT_DISCONNECTED = "client_disconnected"


def _new_event_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class PipelineEvent(_FrozenModel):
    """One thing that happened during one streamed pipeline run.

    `pipeline_stage` is `None` for a pipeline-level event
    (started/completed/failed, heartbeat, client-disconnected) and set
    for a stage-level one. `payload` carries whatever data is specific
    to `event_type` -- see each subclass's own `create` for its exact
    shape.
    """

    event_id: str = Field(default_factory=_new_event_id)
    correlation_id: str
    timestamp: datetime = Field(default_factory=_now)
    pipeline_stage: PipelineStage | None = None
    event_type: PipelineEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class PipelineStartedEvent(PipelineEvent):
    """The run began -- the first event of every stream, always."""

    event_type: Literal[PipelineEventType.PIPELINE_STARTED] = PipelineEventType.PIPELINE_STARTED
    pipeline_stage: None = None

    @classmethod
    def create(cls, *, correlation_id: str, original_question: str) -> PipelineStartedEvent:
        return cls(correlation_id=correlation_id, payload={"original_question": original_question})


class StageStartedEvent(PipelineEvent):
    """One `PipelineStage` began."""

    event_type: Literal[PipelineEventType.STAGE_STARTED] = PipelineEventType.STAGE_STARTED

    @classmethod
    def create(cls, *, correlation_id: str, stage: PipelineStage) -> StageStartedEvent:
        return cls(correlation_id=correlation_id, pipeline_stage=stage)


class StageCompletedEvent(PipelineEvent):
    """One `PipelineStage` finished successfully."""

    event_type: Literal[PipelineEventType.STAGE_COMPLETED] = PipelineEventType.STAGE_COMPLETED

    @classmethod
    def create(
        cls, *, correlation_id: str, stage: PipelineStage, duration_ms: float
    ) -> StageCompletedEvent:
        return cls(
            correlation_id=correlation_id,
            pipeline_stage=stage,
            payload={"duration_ms": duration_ms},
        )


class StageFailedEvent(PipelineEvent):
    """One `PipelineStage`'s own call raised."""

    event_type: Literal[PipelineEventType.STAGE_FAILED] = PipelineEventType.STAGE_FAILED

    @classmethod
    def create(
        cls,
        *,
        correlation_id: str,
        stage: PipelineStage,
        duration_ms: float,
        error: BaseException,
    ) -> StageFailedEvent:
        return cls(
            correlation_id=correlation_id,
            pipeline_stage=stage,
            payload={
                "duration_ms": duration_ms,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )


class PipelineCompletedEvent(PipelineEvent):
    """The run finished without raising. `response.status` may still be `FAILED` (a "soft"
    structured failure, e.g. a rejected execution) -- this fires either way; see
    `payload["status"]`. The client's final event whenever the pipeline did not raise.
    """

    event_type: Literal[PipelineEventType.PIPELINE_COMPLETED] = PipelineEventType.PIPELINE_COMPLETED
    pipeline_stage: None = None

    @classmethod
    def create(cls, *, correlation_id: str, response: QueryMindResponse) -> PipelineCompletedEvent:
        return cls(
            correlation_id=correlation_id,
            payload={
                "status": response.status.value,
                "error": response.error,
                "business_answer": (
                    response.business_answer.model_dump(mode="json")
                    if response.business_answer is not None
                    else None
                ),
            },
        )


class PipelineFailedEvent(PipelineEvent):
    """The run raised. The client's final event whenever the pipeline did raise."""

    event_type: Literal[PipelineEventType.PIPELINE_FAILED] = PipelineEventType.PIPELINE_FAILED

    @classmethod
    def create(
        cls, *, correlation_id: str, error: BaseException, stage: PipelineStage | None = None
    ) -> PipelineFailedEvent:
        return cls(
            correlation_id=correlation_id,
            pipeline_stage=stage,
            payload={"error_type": type(error).__name__, "error_message": str(error)},
        )


class HeartbeatEvent(PipelineEvent):
    """A keep-alive, sent periodically once a run has taken more than a few seconds so far.

    Never carries pipeline data and never affects execution -- see
    `querymind.streaming.subscriber`'s heartbeat task.
    """

    event_type: Literal[PipelineEventType.HEARTBEAT] = PipelineEventType.HEARTBEAT
    pipeline_stage: None = None

    @classmethod
    def create(cls, *, correlation_id: str, elapsed_ms: float) -> HeartbeatEvent:
        return cls(correlation_id=correlation_id, payload={"elapsed_ms": elapsed_ms})


class ClientDisconnectedEvent(PipelineEvent):
    """The client went away mid-stream. Published for observability (`StructuredLogger`) --
    never sent to the client that generated it, since it is already gone.
    """

    event_type: Literal[PipelineEventType.CLIENT_DISCONNECTED] = (
        PipelineEventType.CLIENT_DISCONNECTED
    )
    pipeline_stage: None = None

    @classmethod
    def create(cls, *, correlation_id: str) -> ClientDisconnectedEvent:
        return cls(correlation_id=correlation_id)
