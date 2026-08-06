"""`StageEventPublisher`: the minimal interface `PipelineRunner` depends on to report
progress during a run, without depending on *how* -- or even *whether* -- anything is
listening.

This package (`orchestrator`) must never import `querymind.streaming` (Phase 17):
architecture layering runs presentation -> composition root -> domain engines ->
infrastructure, never the reverse, and streaming is presentation-layer. `StageEventPublisher`
is the seam that lets `querymind.streaming.events.PipelineEventEmitter` (Phase 17) implement
this exact shape -- via structural typing, no inheritance or import required -- and pass
itself into `PipelineRunner.run`/`QueryMindEngine.ask` as `event_publisher`, entirely from
the presentation-layer side of the boundary.

Every method here is a passive, fire-and-forget notification -- `PipelineRunner` awaits
each call in sequence (so an implementation must not block indefinitely) but never inspects
a return value, never lets a publisher's own failure change pipeline behavior beyond what
its caller decides to do with it, and calls these methods purely for their side effect.
`event_publisher` is `None` by default everywhere it appears; the entire pipeline runs
identically whether or not anything is listening -- see the Phase 17 spec's rule 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from querymind.orchestrator.models import PipelineStage

if TYPE_CHECKING:
    from querymind.orchestrator.models import QueryMindResponse


class StageEventPublisher(Protocol):
    """Structural interface for anything that wants to observe one pipeline run in progress."""

    async def pipeline_started(self, *, original_question: str) -> None:
        """The run began -- called once, before the first stage."""
        ...

    async def stage_started(self, stage: PipelineStage) -> None:
        """`stage` began."""
        ...

    async def stage_completed(self, stage: PipelineStage, *, duration_ms: float) -> None:
        """`stage` finished successfully, taking `duration_ms`."""
        ...

    async def stage_failed(
        self, stage: PipelineStage, *, duration_ms: float, error: BaseException
    ) -> None:
        """`stage`'s own call raised `error` after `duration_ms`."""
        ...

    async def pipeline_completed(self, response: QueryMindResponse) -> None:
        """The run finished without raising -- `response.status` may still be `FAILED`
        (a "soft" structured failure, e.g. execution rejected); this fires either way."""
        ...

    async def pipeline_failed(self, *, error: BaseException) -> None:
        """The run raised -- called once, immediately before `PipelineExecutionError`
        propagates out of `PipelineRunner.run`."""
        ...
