"""The End-to-End QueryMind Orchestrator — Phase 15.

The composition root of the QueryMind engine: wires every prior phase's
own public entry point (`querymind.nlu.QueryParser`,
`querymind.schema_linker.SchemaLinker`,
`querymind.business_knowledge.BusinessKnowledgeRegistry`,
`querymind.retrieval.RetrievalEngine`,
`querymind.prompt_compiler.PromptCompiler`,
`querymind.sql_generation.SQLGenerationEngine` (which itself wraps
`querymind.llm.LLMAdapter`), `querymind.sql_validation.SQLValidationEngine`,
`querymind.sql_repair.SQLRepairEngine`,
`querymind.sql_execution.SQLExecutionEngine`,
`querymind.result_formatter.ResultFormatterEngine`) into one sequential
pipeline: a natural language question in, an immutable
`QueryMindResponse` out.

This package generates no SQL, validates no SQL, repairs no SQL, formats
no results, builds no prompts, retrieves no examples, and executes no
SQL itself -- every one of those responsibilities stays entirely with
the phase that already owns it. It only sequences calls into their
public APIs and reports what happened.

Stops at `BusinessAnswer` / `QueryMindResponse` -- no REST API, CLI, UI,
streaming, or production infrastructure is part of this phase.

The public surface is `QueryMindEngine.ask`.
"""

from __future__ import annotations

from querymind.orchestrator.cache import NoOpQueryMindCache, QueryMindCache
from querymind.orchestrator.engine import QueryMindEngine
from querymind.orchestrator.exceptions import (
    PipelineConfigurationError,
    PipelineExecutionError,
    QueryMindError,
)
from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
    StageTiming,
)
from querymind.orchestrator.pipeline import PipelineRunner
from querymind.orchestrator.serializer import QueryMindSerializer
from querymind.orchestrator.statistics import PipelineStatisticsBuilder

__all__ = [
    "NoOpQueryMindCache",
    "PipelineConfigurationError",
    "PipelineExecutionError",
    "PipelineRunner",
    "PipelineStage",
    "PipelineStatistics",
    "PipelineStatisticsBuilder",
    "PipelineStatus",
    "QueryMindCache",
    "QueryMindEngine",
    "QueryMindError",
    "QueryMindResponse",
    "QueryMindSerializer",
    "StageTiming",
]
