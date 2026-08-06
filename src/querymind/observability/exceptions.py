"""Domain-specific exceptions for the Observability package.

Most of this package's own engines (`DiagnosticsEngine`, `HealthCheckEngine`)
deliberately never raise for an ordinary inspection failure -- a
misconfigured or unreachable collaborator becomes a `WARNING`/`ERROR`
finding on the returned report, not an exception (see their own
docstrings for why). These exceptions exist for genuine construction-time
misconfiguration (an invalid `BenchmarkRunner` iteration count, an invalid
`PipelineProfiler` input) and for a `Logger`/`MetricsCollector`
implementation to signal its own internal failure, mirroring every other
phase's `<Phase>Error` hierarchy.
"""

from __future__ import annotations


class ObservabilityError(Exception):
    """Base class for every exception raised within `querymind.observability`."""


class ObservabilityConfigurationError(ObservabilityError):
    """Raised when an observability component is constructed with invalid settings."""


class LoggingError(ObservabilityError):
    """Raised by a `Logger`/`LogSink` implementation for its own genuine failure."""


class MetricsError(ObservabilityError):
    """Raised by a `MetricsCollector` implementation for its own genuine failure."""


class BenchmarkError(ObservabilityError):
    """Raised by `BenchmarkRunner` for a genuine benchmarking failure (not a timed callable's own exception)."""


class ProfilingError(ObservabilityError):
    """Raised by `PipelineProfiler` when given input it cannot profile (e.g. no stages)."""
