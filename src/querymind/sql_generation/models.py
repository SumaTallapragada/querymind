"""Immutable data models for the SQL Generation Engine.

`GeneratedSQL` is the single output type of
`querymind.sql_generation.engine.SQLGenerationEngine.generate` — a
`querymind.prompt_compiler.CompiledPrompt`, sent through the existing
`querymind.llm.LLMAdapter`, turned into extracted, cosmetically
normalized SQL text plus full traceability back to the underlying LLM
call. This package never validates, executes, or repairs SQL —
`GeneratedSQL.sql` is exactly what the LLM produced, extracted and
whitespace/terminator-normalized, nothing more.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from querymind.llm.models import GenerationMetrics
from querymind.query_library.models import SQLDialect


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExtractionMethod(str, Enum):
    """Which strategy `querymind.sql_generation.extractor.SQLExtractor` used to find the SQL."""

    FENCED_SQL_BLOCK = "fenced_sql_block"
    FENCED_GENERIC_BLOCK = "fenced_generic_block"
    RAW_TEXT = "raw_text"


class SQLStatementType(str, Enum):
    """The leading SQL keyword, sniffed by `querymind.sql_generation.parser.StatementTypeDetector`.

    A shallow, deterministic prefix match — not a real SQL parser or
    validator. It exists purely as descriptive metadata about the
    generated artifact; nothing in this package uses it to make
    decisions about the SQL's correctness.
    """

    SELECT = "select"
    WITH = "with"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    UNKNOWN = "unknown"


class SQLGenerationStatistics(_FrozenModel):
    """Observability data about one `SQLGenerationEngine.generate` call."""

    extraction_method: ExtractionMethod
    raw_sql_length: int = Field(
        ge=0, description="Character length of the extracted SQL, pre-normalization."
    )
    normalized_sql_length: int = Field(
        ge=0, description="Character length of the final normalized SQL."
    )
    normalization_changed_sql: bool = Field(
        description="Whether normalization altered the extracted text at all."
    )
    generation_latency_ms: float = Field(
        ge=0.0,
        description="Wall-clock time SQLGenerationEngine.generate took, including the LLM call.",
    )


class GeneratedSQL(_FrozenModel):
    """The complete output of one generation: normalized SQL text plus full traceability."""

    sql: str = Field(min_length=1, description="The final, normalized SQL text.")
    statement_type: SQLStatementType
    raw_llm_content: str = Field(
        description="The LLMResponse.content this was extracted from, completely unmodified."
    )
    dialect: SQLDialect = Field(
        description="Carried over from the CompiledPrompt that produced this."
    )
    llm_metrics: GenerationMetrics = Field(
        description="The underlying LLM call's own metrics, unmodified."
    )
    statistics: SQLGenerationStatistics
