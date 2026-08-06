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

Stops at `BusinessAnswer` / `QueryMindResponse` -- this package itself
exposes no REST API, CLI, UI, or streaming transport; `querymind.api`
(Phase 16) is the presentation layer that calls `QueryMindEngine` over
HTTP, and `querymind.streaming` (Phase 17) is the presentation layer
that streams its progress over SSE/WebSockets -- both call `ask`, never
duplicate its sequencing.

The public surface is `QueryMindEngine.ask` (and, added in Phase 16 for
the FastAPI service layer's `/query/sql`/`/query/repair` endpoints,
`QueryMindEngine.ask_for_sql`/`.repair`). `StageEventPublisher` (Phase
17) is the structural interface `ask`'s optional `event_publisher`
parameter accepts -- defined here, not in `querymind.streaming`, so this
package never depends on the presentation layer; see
`querymind.orchestrator.events`.
"""

from __future__ import annotations

from querymind.orchestrator.cache import NoOpQueryMindCache, QueryMindCache
from querymind.orchestrator.engine import QueryMindEngine
from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.exceptions import (
    PipelineConfigurationError,
    PipelineExecutionError,
    QueryMindError,
)
from querymind.orchestrator.models import (
    GeneratedSqlResult,
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
    "GeneratedSqlResult",
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
    "StageEventPublisher",
    "StageTiming",
]
