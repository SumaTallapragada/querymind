"""PipelineStatisticsBuilder: assembles a `PipelineStatistics` from what a pipeline run measured.

A single source of truth for building this one model, used by both
`PipelineRunner` (on a completed run) and `QueryMindEngine` (when
converting a caught `PipelineExecutionError`'s partial data into a
`FAILED` response) -- so the two call sites can never disagree about how
`PipelineStatistics` is assembled.
"""

from __future__ import annotations

from querymind.orchestrator.models import PipelineStatistics, StageTiming


class PipelineStatisticsBuilder:
    """Builds a `PipelineStatistics`. Pure data assembly, no timing measurement of its own."""

    def build(
        self,
        *,
        total_latency_ms: float,
        stage_timings: tuple[StageTiming, ...],
        repair_attempted: bool,
        repair_performed: bool,
    ) -> PipelineStatistics:
        return PipelineStatistics(
            total_latency_ms=total_latency_ms,
            stage_timings=stage_timings,
            repair_attempted=repair_attempted,
            repair_performed=repair_performed,
        )
