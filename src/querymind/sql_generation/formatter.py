"""Renders a `GeneratedSQL` into a human-readable display string.

A standalone convenience, not part of `SQLGenerationEngine.generate`'s
pipeline itself — the pipeline's actual output is the structured
`GeneratedSQL` object. This exists for callers that want a quick,
readable summary (a CLI, a log line, a debugging session) without
reaching into `GeneratedSQL`'s fields themselves.
"""

from __future__ import annotations

from querymind.sql_generation.models import GeneratedSQL


class GeneratedSQLFormatter:
    """Formats a `GeneratedSQL` as one string: a metadata comment header, then the SQL."""

    def format(self, generated: GeneratedSQL) -> str:
        """Return `generated` as one human-readable string."""
        usage = generated.llm_metrics.token_usage
        header = (
            f"-- dialect: {generated.dialect.value} | statement: {generated.statement_type.value} "
            f"| tokens: {usage.prompt_tokens} in / {usage.completion_tokens} out "
            f"| latency: {generated.llm_metrics.latency_ms:.1f}ms"
        )
        return f"{header}\n{generated.sql}"
