"""PipelineProfiler: a pure, read-only analysis of already-measured stage durations.

Takes a plain, ordered sequence of `(stage_name, latency_ms)` pairs --
never a live pipeline, never `orchestrator.PipelineStatistics` directly
(this package does not import `orchestrator`, for the same reason
`models.py` documents: staying usable to profile a single phase in
isolation, with no orchestrator involved at all). A caller integrating
this with real `PipelineStatistics.stage_timings` converts each
`StageTiming` to a `(stage.value, latency_ms)` tuple first -- a one-line,
call-site conversion, not something this module needs to know about.

"Do not instrument external libraries" (the mandatory rule this module
was built under): `PipelineProfiler` never wraps, patches, or times
anything itself -- every duration it works with was already measured by
the caller (e.g. via `StageInstrumentation` or `BenchmarkRunner`) before
being handed to `profile()`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from querymind.observability.exceptions import ProfilingError
from querymind.observability.models import PipelineProfile, ProfilingStatistics


class PipelineProfiler:
    """Computes cumulative latency and each stage's percentage share of total measured runtime."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    def profile(self, stage_durations: Sequence[tuple[str, float]]) -> PipelineProfile:
        """Profile `stage_durations`, an ordered `(stage_name, latency_ms)` sequence.

        Order matters: `cumulative_latency_ms` accumulates in the given
        order, so pass stages in the order they actually ran.

        Raises `ProfilingError` if `stage_durations` is empty -- there is
        no meaningful "dominant stage" or percentage breakdown for zero
        measured stages.
        """
        if not stage_durations:
            raise ProfilingError("Cannot profile an empty sequence of stage durations.")

        total_latency_ms = sum(latency_ms for _, latency_ms in stage_durations)

        stage_statistics: list[ProfilingStatistics] = []
        cumulative_ms = 0.0
        for stage, latency_ms in stage_durations:
            cumulative_ms += latency_ms
            percentage = (latency_ms / total_latency_ms * 100) if total_latency_ms > 0 else 0.0
            stage_statistics.append(
                ProfilingStatistics(
                    stage=stage,
                    latency_ms=latency_ms,
                    cumulative_latency_ms=cumulative_ms,
                    percentage_of_total=percentage,
                )
            )

        dominant = max(stage_statistics, key=lambda s: s.latency_ms)

        return PipelineProfile(
            stage_statistics=tuple(stage_statistics),
            total_latency_ms=total_latency_ms,
            dominant_stage=dominant.stage,
            dominant_stage_percentage=dominant.percentage_of_total,
            generated_at=self._clock(),
        )
