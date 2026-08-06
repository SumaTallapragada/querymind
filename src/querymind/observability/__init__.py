"""Observability, logging, metrics, benchmarking, and diagnostics — QueryMind Phase 15.6.

A passive, framework-independent operational layer for the whole
QueryMind pipeline: structured logging (`logger.py`), passive metrics
collection (`metrics.py`), an optional benchmarking harness
(`benchmark.py`), read-only, non-raising diagnostics
(`diagnostics.py`), lightweight health checks (`health.py`), and
pipeline latency profiling (`profiler.py`).

This package never changes pipeline behavior. Nothing here executes SQL,
mutates a pipeline model, or hardcodes a logging/metrics backend
(structlog, Prometheus, OpenTelemetry, or otherwise) — every component is
constructor-injected, matching every other phase in this project, and
every engine that inspects other phases (`DiagnosticsEngine`,
`HealthCheckEngine`) does so exclusively through their public APIs.

`querymind.orchestrator` and every pipeline phase remain entirely
unaware this package exists — instrumentation is added at the call site
(see `logger.StageInstrumentation`'s docstring), never by editing a
phase's own source.

There is no single public entry point the way most phases have one --
each concern (logging, metrics, benchmarking, diagnostics, health,
profiling) is its own small, independently usable engine.
"""

from __future__ import annotations

from querymind.observability.benchmark import (
    DEFAULT_MEASURED_ITERATIONS,
    DEFAULT_WARMUP_ITERATIONS,
    BenchmarkRunner,
)
from querymind.observability.cache import NoOpObservabilityCache, ObservabilityCache
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.exceptions import (
    BenchmarkError,
    LoggingError,
    MetricsError,
    ObservabilityConfigurationError,
    ObservabilityError,
    ProfilingError,
)
from querymind.observability.health import HealthCheckEngine
from querymind.observability.logger import (
    InMemoryLogSink,
    Logger,
    LogSink,
    StageInstrumentation,
    StdoutLogSink,
    StructuredLogger,
    generate_correlation_id,
)
from querymind.observability.metrics import InMemoryMetricsCollector, MetricsCollector
from querymind.observability.models import (
    BenchmarkReport,
    BenchmarkResult,
    DiagnosticFinding,
    DiagnosticsReport,
    DiagnosticStatus,
    HealthCheck,
    HealthReport,
    HealthStatus,
    LogEvent,
    LogEventType,
    LogLevel,
    MetricsSnapshot,
    PipelineProfile,
    ProfilingStatistics,
    StageMetric,
    StructuredLogRecord,
)
from querymind.observability.profiler import PipelineProfiler
from querymind.observability.serializer import ObservabilitySerializer

__all__ = [
    "DEFAULT_MEASURED_ITERATIONS",
    "DEFAULT_WARMUP_ITERATIONS",
    "BenchmarkError",
    "BenchmarkReport",
    "BenchmarkResult",
    "BenchmarkRunner",
    "DiagnosticFinding",
    "DiagnosticStatus",
    "DiagnosticsEngine",
    "DiagnosticsReport",
    "HealthCheck",
    "HealthCheckEngine",
    "HealthReport",
    "HealthStatus",
    "InMemoryLogSink",
    "InMemoryMetricsCollector",
    "LogEvent",
    "LogEventType",
    "LogLevel",
    "LogSink",
    "Logger",
    "LoggingError",
    "MetricsCollector",
    "MetricsError",
    "MetricsSnapshot",
    "NoOpObservabilityCache",
    "ObservabilityCache",
    "ObservabilityConfigurationError",
    "ObservabilityError",
    "ObservabilitySerializer",
    "PipelineProfile",
    "PipelineProfiler",
    "ProfilingError",
    "ProfilingStatistics",
    "StageInstrumentation",
    "StageMetric",
    "StdoutLogSink",
    "StructuredLogRecord",
    "StructuredLogger",
    "generate_correlation_id",
]
