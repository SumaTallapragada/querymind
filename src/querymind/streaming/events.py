"""PipelineEventEmitter: bridges `PipelineRunner`'s stage-by-stage callbacks into `PipelineEvent`s.

`querymind.orchestrator.events.StageEventPublisher` defines the callback
shape `PipelineRunner.run`/`QueryMindEngine.ask` call into -- a
structural `Protocol` with no dependency on this package. This class is
the concrete implementation passed as `event_publisher` for every
streamed request: it is the one place in `querymind.streaming` that
knows both what a stage callback looks like and what a `PipelineEvent`
looks like, translating one into the other and handing it to an
injected `EventPublisher`. Every other module in this package deals with
only one side of that translation.
"""

from __future__ import annotations

from querymind.orchestrator.models import PipelineStage, QueryMindResponse
from querymind.streaming.models import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageStartedEvent,
)
from querymind.streaming.publisher import EventPublisher


class PipelineEventEmitter:
    """A `StageEventPublisher` (structurally) bound to one `correlation_id` and one
    `EventPublisher`. Constructed fresh per streamed request -- never shared or reused across
    requests -- so its only state is the `correlation_id` it closes over.
    """

    def __init__(self, publisher: EventPublisher, *, correlation_id: str) -> None:
        self._publisher = publisher
        self._correlation_id = correlation_id

    async def pipeline_started(self, *, original_question: str) -> None:
        await self._publisher.publish(
            PipelineStartedEvent.create(
                correlation_id=self._correlation_id, original_question=original_question
            )
        )

    async def stage_started(self, stage: PipelineStage) -> None:
        await self._publisher.publish(
            StageStartedEvent.create(correlation_id=self._correlation_id, stage=stage)
        )

    async def stage_completed(self, stage: PipelineStage, *, duration_ms: float) -> None:
        await self._publisher.publish(
            StageCompletedEvent.create(
                correlation_id=self._correlation_id, stage=stage, duration_ms=duration_ms
            )
        )

    async def stage_failed(
        self, stage: PipelineStage, *, duration_ms: float, error: BaseException
    ) -> None:
        await self._publisher.publish(
            StageFailedEvent.create(
                correlation_id=self._correlation_id,
                stage=stage,
                duration_ms=duration_ms,
                error=error,
            )
        )

    async def pipeline_completed(self, response: QueryMindResponse) -> None:
        await self._publisher.publish(
            PipelineCompletedEvent.create(correlation_id=self._correlation_id, response=response)
        )

    async def pipeline_failed(self, *, error: BaseException) -> None:
        await self._publisher.publish(
            PipelineFailedEvent.create(correlation_id=self._correlation_id, error=error)
        )
