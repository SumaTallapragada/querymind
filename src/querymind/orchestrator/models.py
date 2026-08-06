"""Immutable data models for the End-to-End QueryMind Orchestrator.

`QueryMindResponse` is the single output type of
`querymind.orchestrator.engine.QueryMindEngine.ask` -- every prior
phase's own result type (`GeneratedSQL`, `SQLValidationResult`,
`SQLRepairResult`, `SQLExecutionResult`, `BusinessAnswer`) is reused
directly here, never duplicated, exactly as produced by that phase's own
public entry point.

Every model is frozen (`model_config = ConfigDict(frozen=True,
extra="forbid")`) and uses `tuple`, never `list`, for collections --
matching every other phase's models package.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from querymind.result_formatter import BusinessAnswer
from querymind.sql_execution import SQLExecutionResult
from querymind.sql_generation import GeneratedSQL
from querymind.sql_repair import SQLRepairResult
from querymind.sql_validation import SQLValidationResult


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PipelineStage(str, Enum):
    """Every independently timed stage of the end-to-end pipeline, in execution order."""

    NLU = "nlu"
    SCHEMA_LINKING = "schema_linking"
    BUSINESS_KNOWLEDGE = "business_knowledge"
    RETRIEVAL = "retrieval"
    PROMPT_COMPILATION = "prompt_compilation"
    LLM = "llm"
    SQL_GENERATION = "sql_generation"
    SQL_VALIDATION = "sql_validation"
    SQL_REPAIR = "sql_repair"
    SQL_EXECUTION = "sql_execution"
    RESULT_FORMATTING = "result_formatting"


class StageTiming(_FrozenModel):
    """How long one `PipelineStage` took, in isolation."""

    stage: PipelineStage
    latency_ms: float = Field(ge=0.0)


class PipelineStatistics(_FrozenModel):
    """Observability data about one `QueryMindEngine.ask` call."""

    total_latency_ms: float = Field(ge=0.0, description="Wall-clock time the whole call took.")
    stage_timings: tuple[StageTiming, ...] = Field(
        description="One entry per stage that actually ran and completed, in execution order."
    )
    repair_attempted: bool = Field(description="Whether SQL_VALIDATION reported the SQL invalid.")
    repair_performed: bool = Field(
        description="Whether SQL_REPAIR was attempted AND produced SQL that validated as valid."
    )


class PipelineStatus(str, Enum):
    """The terminal outcome of one `QueryMindEngine.ask` call."""

    SUCCESS = "success"
    FAILED = "failed"


class QueryMindResponse(_FrozenModel):
    """The complete output of one end-to-end question. `QueryMindEngine.ask` always returns one.

    `generated_sql`/`validation_result` always describe the SQL
    ultimately executed -- if repair ran, that is the repaired SQL and
    its own validation result (`repair_result.final_sql`/
    `.final_validation_result`), never the original invalid SQL.
    `repair_result` is `None` whenever repair never ran (validation
    passed the first time).
    """

    original_question: str
    business_answer: BusinessAnswer | None = Field(
        default=None, description="Populated only when status is SUCCESS."
    )
    generated_sql: GeneratedSQL | None = Field(
        default=None,
        description="The SQL ultimately executed -- the repaired SQL if repair ran, else the "
        "first SQL SQL_GENERATION produced. None if no SQL was ever generated.",
    )
    validation_result: SQLValidationResult | None = Field(
        default=None, description="The validation result for generated_sql, specifically."
    )
    repair_result: SQLRepairResult | None = Field(
        default=None, description="None whenever repair never ran."
    )
    execution_result: SQLExecutionResult | None = Field(default=None)
    statistics: PipelineStatistics
    status: PipelineStatus
    error: str | None = Field(default=None, description="Populated only when status is FAILED.")
