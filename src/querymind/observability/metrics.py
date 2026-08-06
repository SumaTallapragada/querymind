"""Passive metrics collection: a `MetricsCollector` Protocol and a default,
in-memory implementation.

"Passive" means exactly what it says: nothing in this module ever mutates
a pipeline model or an engine's output -- every `record_*` method only
updates this collector's *own* private bookkeeping (counters, latency
totals), which is not global or shared state (see `InMemoryMetricsCollector`'s
own docstring). `snapshot()` reads that bookkeeping into a new, immutable
`MetricsSnapshot` -- it never hands out the mutable internals themselves.

No Prometheus, OpenTelemetry, or any other metrics backend is integrated
here -- `MetricsSnapshot` is a plain Pydantic model a caller can export
(via `observability.serializer.ObservabilitySerializer`) to whatever
system they choose.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from querymind.observability.models import MetricsSnapshot, StageMetric


class MetricsCollector(Protocol):
    """Injectable interface for observing pipeline execution. Every method is fire-and-forget."""

    def record_pipeline_run(
        self, *, success: bool, latency_ms: float, repair_attempted: bool, repair_succeeded: bool
    ) -> None:
        """Record the outcome of one complete end-to-end pipeline run."""
        ...

    def record_stage_latency(self, stage: str, latency_ms: float) -> None:
        """Record one stage's measured latency for one call."""
        ...

    def record_validation_failure(self) -> None:
        """Record that one SQL validation attempt reported at least one error."""
        ...

    def record_sql_execution(self, *, rows_returned: int) -> None:
        """Record one successful SQL execution and how many rows it returned."""
        ...

    def record_llm_token_usage(self, *, prompt_tokens: int, completion_tokens: int) -> None:
        """Record one LLM call's token usage."""
        ...

    def record_cache_access(self, *, hit: bool) -> None:
        """Record one cache lookup's outcome."""
        ...

    def record_startup_time(self, duration_ms: float) -> None:
        """Record how long process/engine startup took. Expected to be called at most once."""
        ...

    def snapshot(self) -> MetricsSnapshot:
        """Return an immutable, point-in-time read of everything observed so far."""
        ...


class InMemoryMetricsCollector:
    """The default `MetricsCollector`: accumulates counters in ordinary instance attributes.

    Not global or shared state -- every `InMemoryMetricsCollector` a
    caller constructs owns its own independent counters, exactly like any
    other constructor-injected collaborator in this project. A caller
    who wants metrics shared across multiple components passes the same
    *instance* to each of them, the same way a `DatabaseConnectionProvider`
    or `MetadataRegistry` is shared today -- this class introduces no
    module-level singleton to make that possible.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

        self._pipeline_run_count = 0
        self._pipeline_success_count = 0
        self._pipeline_failure_count = 0
        self._pipeline_latency_total_ms = 0.0

        self._stage_call_counts: dict[str, int] = {}
        self._stage_latency_totals: dict[str, float] = {}
        self._stage_latency_mins: dict[str, float] = {}
        self._stage_latency_maxs: dict[str, float] = {}

        self._validation_failure_count = 0
        self._repair_attempted_count = 0
        self._repair_success_count = 0

        self._sql_execution_count = 0
        self._total_rows_returned = 0

        self._llm_prompt_tokens = 0
        self._llm_completion_tokens = 0

        self._cache_hit_count = 0
        self._cache_miss_count = 0

        self._startup_time_ms: float | None = None

    def record_pipeline_run(
        self, *, success: bool, latency_ms: float, repair_attempted: bool, repair_succeeded: bool
    ) -> None:
        self._pipeline_run_count += 1
        self._pipeline_latency_total_ms += latency_ms
        if success:
            self._pipeline_success_count += 1
        else:
            self._pipeline_failure_count += 1
        if repair_attempted:
            self._repair_attempted_count += 1
            if repair_succeeded:
                self._repair_success_count += 1

    def record_stage_latency(self, stage: str, latency_ms: float) -> None:
        self._stage_call_counts[stage] = self._stage_call_counts.get(stage, 0) + 1
        self._stage_latency_totals[stage] = self._stage_latency_totals.get(stage, 0.0) + latency_ms
        self._stage_latency_mins[stage] = min(
            self._stage_latency_mins.get(stage, latency_ms), latency_ms
        )
        self._stage_latency_maxs[stage] = max(
            self._stage_latency_maxs.get(stage, latency_ms), latency_ms
        )

    def record_validation_failure(self) -> None:
        self._validation_failure_count += 1

    def record_sql_execution(self, *, rows_returned: int) -> None:
        self._sql_execution_count += 1
        self._total_rows_returned += rows_returned

    def record_llm_token_usage(self, *, prompt_tokens: int, completion_tokens: int) -> None:
        self._llm_prompt_tokens += prompt_tokens
        self._llm_completion_tokens += completion_tokens

    def record_cache_access(self, *, hit: bool) -> None:
        if hit:
            self._cache_hit_count += 1
        else:
            self._cache_miss_count += 1

    def record_startup_time(self, duration_ms: float) -> None:
        self._startup_time_ms = duration_ms

    def snapshot(self) -> MetricsSnapshot:
        stage_metrics = tuple(
            StageMetric(
                stage=stage,
                call_count=count,
                total_latency_ms=self._stage_latency_totals[stage],
                average_latency_ms=self._stage_latency_totals[stage] / count,
                min_latency_ms=self._stage_latency_mins[stage],
                max_latency_ms=self._stage_latency_maxs[stage],
            )
            for stage, count in self._stage_call_counts.items()
        )
        average_pipeline_latency_ms = (
            self._pipeline_latency_total_ms / self._pipeline_run_count
            if self._pipeline_run_count > 0
            else 0.0
        )
        repair_success_rate = (
            self._repair_success_count / self._repair_attempted_count
            if self._repair_attempted_count > 0
            else 0.0
        )
        return MetricsSnapshot(
            captured_at=self._clock(),
            pipeline_run_count=self._pipeline_run_count,
            pipeline_success_count=self._pipeline_success_count,
            pipeline_failure_count=self._pipeline_failure_count,
            average_pipeline_latency_ms=average_pipeline_latency_ms,
            stage_metrics=stage_metrics,
            validation_failure_count=self._validation_failure_count,
            repair_attempted_count=self._repair_attempted_count,
            repair_success_count=self._repair_success_count,
            repair_success_rate=repair_success_rate,
            sql_execution_count=self._sql_execution_count,
            total_rows_returned=self._total_rows_returned,
            llm_prompt_tokens=self._llm_prompt_tokens,
            llm_completion_tokens=self._llm_completion_tokens,
            cache_hit_count=self._cache_hit_count,
            cache_miss_count=self._cache_miss_count,
            startup_time_ms=self._startup_time_ms,
        )
