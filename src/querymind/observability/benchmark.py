"""Benchmarking: `BenchmarkRunner`, a warmup-then-measure timing harness.

Deliberately pipeline-agnostic -- this module never imports `nlu`,
`sql_generation`, or any other phase. `BenchmarkRunner.run` times any
zero-argument callable a caller supplies (typically a small lambda
wrapping one phase's real call, e.g. `lambda: parser.parse(question)`);
benchmarking a specific stage is the caller's responsibility, not
something hardcoded here. This keeps `observability` decoupled from
every pipeline package's internals and reusable for benchmarking
anything, not just this project's own pipeline.

"Completely optional" (the mandatory rule this module was built under)
follows directly from this design: nothing in `sql_generation`,
`orchestrator`, or any other phase imports `BenchmarkRunner` or is even
aware it exists, so there is no production code path where benchmarking
could add overhead -- it only ever runs when a caller explicitly
constructs a `BenchmarkRunner` and calls it.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from querymind.observability.exceptions import BenchmarkError
from querymind.observability.models import BenchmarkReport, BenchmarkResult

#: Default warmup/measured iteration counts -- small enough that a benchmark suite covering
#: every pipeline stage still runs in well under a second for cheap, in-memory stages.
DEFAULT_WARMUP_ITERATIONS = 1
DEFAULT_MEASURED_ITERATIONS = 5


class BenchmarkRunner:
    """Runs a callable through warmup iterations (discarded) then measured iterations (kept).

    `warmup_iterations`/`measured_iterations` set the defaults for every
    `run`/`run_async` call; either can be overridden per call.
    """

    def __init__(
        self,
        warmup_iterations: int = DEFAULT_WARMUP_ITERATIONS,
        measured_iterations: int = DEFAULT_MEASURED_ITERATIONS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if warmup_iterations < 0:
            raise BenchmarkError(f"warmup_iterations must be >= 0, got {warmup_iterations!r}.")
        if measured_iterations < 1:
            raise BenchmarkError(f"measured_iterations must be >= 1, got {measured_iterations!r}.")
        self._default_warmup_iterations = warmup_iterations
        self._default_measured_iterations = measured_iterations
        self._clock = clock if clock is not None else time.perf_counter

    def run(
        self,
        name: str,
        fn: Callable[[], object],
        *,
        warmup_iterations: int | None = None,
        measured_iterations: int | None = None,
    ) -> BenchmarkResult:
        """Time `fn`, called with no arguments, over warmup then measured iterations."""
        warmup = self._default_warmup_iterations if warmup_iterations is None else warmup_iterations
        measured = (
            self._default_measured_iterations
            if measured_iterations is None
            else measured_iterations
        )
        for _ in range(warmup):
            fn()

        samples_ms = []
        for _ in range(measured):
            started = self._clock()
            fn()
            samples_ms.append((self._clock() - started) * 1000)

        return self._build_result(name, warmup, samples_ms)

    async def run_async(
        self,
        name: str,
        fn: Callable[[], Awaitable[object]],
        *,
        warmup_iterations: int | None = None,
        measured_iterations: int | None = None,
    ) -> BenchmarkResult:
        """Time an async `fn`, awaited with no arguments, over warmup then measured iterations."""
        warmup = self._default_warmup_iterations if warmup_iterations is None else warmup_iterations
        measured = (
            self._default_measured_iterations
            if measured_iterations is None
            else measured_iterations
        )
        for _ in range(warmup):
            await fn()

        samples_ms = []
        for _ in range(measured):
            started = self._clock()
            await fn()
            samples_ms.append((self._clock() - started) * 1000)

        return self._build_result(name, warmup, samples_ms)

    @staticmethod
    def _build_result(
        name: str, warmup_iterations: int, samples_ms: list[float]
    ) -> BenchmarkResult:
        sorted_samples = sorted(samples_ms)
        return BenchmarkResult(
            name=name,
            warmup_iterations=warmup_iterations,
            measured_iterations=len(samples_ms),
            average_ms=statistics.mean(samples_ms),
            min_ms=sorted_samples[0],
            max_ms=sorted_samples[-1],
            median_ms=statistics.median(samples_ms),
            p95_ms=BenchmarkRunner._percentile(sorted_samples, 0.95),
        )

    @staticmethod
    def _percentile(sorted_samples: list[float], fraction: float) -> float:
        """Nearest-rank percentile: no interpolation, always one of the actual samples.

        Simple and deterministic, which matters more than statistical
        rigor for the small sample counts (typically single digits) a
        benchmark run actually produces.
        """
        if len(sorted_samples) == 1:
            return sorted_samples[0]
        index = max(
            0, min(len(sorted_samples) - 1, int(len(sorted_samples) * fraction + 0.9999) - 1)
        )
        return sorted_samples[index]

    @staticmethod
    def report(
        results: tuple[BenchmarkResult, ...], clock: Callable[[], datetime] | None = None
    ) -> BenchmarkReport:
        """Assemble every `BenchmarkResult` from one benchmarking run into a `BenchmarkReport`."""
        generated_at = clock() if clock is not None else datetime.now(UTC)
        return BenchmarkReport(results=results, generated_at=generated_at)
