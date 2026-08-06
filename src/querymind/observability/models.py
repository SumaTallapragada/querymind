"""Immutable data models for the Observability package.

Every model here is a passive record of something *observed* -- a log
event, a measured latency, an inspection finding -- never an input that
influences pipeline behavior. Nothing in this module is consumed by any
pipeline phase; these models flow only from `querymind.observability`'s
own engines back out to whatever operator or test is using them.

Every model is frozen (`model_config = ConfigDict(frozen=True,
extra="forbid")`) and uses `tuple`, never `list`, for collections --
matching every other package's models module in this project.

`stage` fields throughout this module are plain `str`, not
`querymind.orchestrator.models.PipelineStage` -- this package must stay
usable to instrument or benchmark a single phase in isolation (e.g. just
`nlu`, with no orchestrator involved at all), so it never imports
`orchestrator` and never assumes a caller has one.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Structured logging ---------------------------------------------------------------------


class LogLevel(str, Enum):
    """Standard log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogEventType(str, Enum):
    """The lifecycle point one `LogEvent` represents for a named stage."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class LogEvent(_FrozenModel):
    """One thing that happened during execution of a named stage.

    The input to `Logger.event` -- a semantic record of "this stage
    started/completed/failed," independent of how it will eventually be
    rendered as a `StructuredLogRecord`.
    """

    stage: str = Field(description="Free-form stage name, e.g. 'nlu', 'sql_execution'.")
    event_type: LogEventType
    timestamp: datetime
    correlation_id: str | None = Field(
        default=None, description="Ties every event for one end-to-end run together."
    )
    request_id: str | None = Field(
        default=None, description="Ties every event for one inbound request together."
    )
    duration_ms: float | None = Field(
        default=None, ge=0.0, description="Populated on COMPLETED/FAILED, not STARTED."
    )
    error_type: str | None = Field(
        default=None, description="The failing exception's class name. Populated only on FAILED."
    )
    error_message: str | None = Field(
        default=None, description="The failing exception's message. Populated only on FAILED."
    )


class StructuredLogRecord(_FrozenModel):
    """One fully-rendered, JSON-friendly structured log record, ready for a `LogSink`.

    Every field is a JSON-safe primitive -- no embedded objects, no
    string-concatenated message combining fields the way `f"{stage} took
    {ms}ms"` would. A `LogSink` only ever needs to serialize this model.
    """

    level: LogLevel
    message: str
    timestamp: datetime
    stage: str | None = None
    event_type: LogEventType | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)
    error_type: str | None = None
    error_message: str | None = None


# --- Metrics -----------------------------------------------------------------------------------


class StageMetric(_FrozenModel):
    """Aggregated latency statistics for one named stage, across every call observed so far."""

    stage: str
    call_count: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0.0)
    average_latency_ms: float = Field(ge=0.0)
    min_latency_ms: float = Field(ge=0.0)
    max_latency_ms: float = Field(ge=0.0)


class MetricsSnapshot(_FrozenModel):
    """An immutable, point-in-time read of everything a `MetricsCollector` has observed so far.

    Calling `MetricsCollector.snapshot()` again later returns a new,
    independent `MetricsSnapshot` -- this one is never updated in place.
    """

    captured_at: datetime
    pipeline_run_count: int = Field(ge=0)
    pipeline_success_count: int = Field(ge=0)
    pipeline_failure_count: int = Field(ge=0)
    average_pipeline_latency_ms: float = Field(ge=0.0)
    stage_metrics: tuple[StageMetric, ...] = Field(default=())
    validation_failure_count: int = Field(ge=0)
    repair_attempted_count: int = Field(ge=0)
    repair_success_count: int = Field(ge=0)
    repair_success_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="repair_success_count / repair_attempted_count, or 0.0 if none attempted.",
    )
    sql_execution_count: int = Field(ge=0)
    total_rows_returned: int = Field(ge=0)
    llm_prompt_tokens: int = Field(ge=0)
    llm_completion_tokens: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    cache_miss_count: int = Field(ge=0)
    startup_time_ms: float | None = Field(default=None, ge=0.0)


# --- Benchmarking --------------------------------------------------------------------------------


class BenchmarkResult(_FrozenModel):
    """Timing statistics for one benchmarked callable, over its measured iterations."""

    name: str
    warmup_iterations: int = Field(ge=0)
    measured_iterations: int = Field(ge=1)
    average_ms: float = Field(ge=0.0)
    min_ms: float = Field(ge=0.0)
    max_ms: float = Field(ge=0.0)
    median_ms: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)


class BenchmarkReport(_FrozenModel):
    """Every `BenchmarkResult` from one benchmarking run, in the order they were measured."""

    results: tuple[BenchmarkResult, ...]
    generated_at: datetime


# --- Diagnostics -----------------------------------------------------------------------------------


class DiagnosticStatus(str, Enum):
    """The outcome of one diagnostic check."""

    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticFinding(_FrozenModel):
    """One diagnostic check's result -- never raised, always reported."""

    check_name: str
    status: DiagnosticStatus
    message: str
    details: str | None = None


class DiagnosticsReport(_FrozenModel):
    """Every `DiagnosticFinding` from one `DiagnosticsEngine.run()` call.

    `overall_status` is the worst status among `findings` (`ERROR` >
    `WARNING` > `PASS`) -- computed once by `DiagnosticsEngine`, not
    re-derived by every reader of this model.
    """

    findings: tuple[DiagnosticFinding, ...]
    overall_status: DiagnosticStatus
    generated_at: datetime


# --- Health checks -----------------------------------------------------------------------------------


class HealthStatus(str, Enum):
    """The outcome of one health check."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheck(_FrozenModel):
    """One health check's result."""

    name: str
    status: HealthStatus
    message: str | None = None


class HealthReport(_FrozenModel):
    """Every `HealthCheck` from one `HealthCheckEngine.check()` call.

    `overall_status` is `HEALTHY` only if every check is `HEALTHY`;
    `UNHEALTHY` if any check is `UNHEALTHY`; otherwise `UNKNOWN`.
    """

    checks: tuple[HealthCheck, ...]
    overall_status: HealthStatus
    generated_at: datetime


# --- Profiling -----------------------------------------------------------------------------------


class ProfilingStatistics(_FrozenModel):
    """One stage's share of the total profiled runtime."""

    stage: str
    latency_ms: float = Field(ge=0.0)
    cumulative_latency_ms: float = Field(ge=0.0)
    percentage_of_total: float = Field(ge=0.0, le=100.0)


class PipelineProfile(_FrozenModel):
    """A complete latency breakdown across every profiled stage, in the order they ran."""

    stage_statistics: tuple[ProfilingStatistics, ...]
    total_latency_ms: float = Field(ge=0.0)
    dominant_stage: str
    dominant_stage_percentage: float = Field(ge=0.0, le=100.0)
    generated_at: datetime
