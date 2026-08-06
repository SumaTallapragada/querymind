# Glossary

Terminology used throughout this codebase and its documentation, grouped
by where each term first appears in the pipeline. See
[`SYSTEM_DESIGN.md`](../SYSTEM_DESIGN.md) for the full model-by-model
walkthrough these definitions summarize.

## Pipeline models

**QueryContext** — The structured interpretation of a raw natural language
question, produced by `nlu.QueryParser.parse`. Carries `intent`,
business-concept *names* (`primary_entity`, `metrics`, `filters`, ...),
and time/sort/limit expressions — nothing here has touched the database
yet.

**LinkedQueryContext** — `QueryContext`'s business-concept names resolved
against the real schema, produced by `schema_linker.SchemaLinker.link`.
Business concepts become `ResolvedTable`/`ResolvedMetric`/`ResolvedColumn`
instances carrying real `TableMetadata`/`ColumnMetadata`; anything that
couldn't be resolved unambiguously is recorded as an `Ambiguity` instead
of guessed.

**RetrievedKnowledgeBundle** — A `LinkedQueryContext` plus the top-K most
relevant few-shot examples from the Query Intelligence Library, produced
by `retrieval.RetrievalEngine.retrieve`. Each retrieved example carries a
`SignalBreakdown` explaining its score.

**CompiledPrompt** — The complete, assembled LLM prompt, produced by
`prompt_compiler.PromptCompiler.compile`: seven independent sections plus
`PromptStatistics`, rendered to text via `.as_text()`.

**LLMResponse** — Raw text plus `GenerationMetrics` (provider, model,
latency, token usage, retries, finish reason), produced by
`llm.LLMAdapter.generate` — called internally by SQL Generation, not
directly by the orchestrator.

**GeneratedSQL** — The final, normalized SQL text plus its detected
statement type, dialect, and the underlying `LLMResponse`'s own metrics,
produced by `sql_generation.SQLGenerationEngine.generate`.

**SQLValidationResult** — Whether `GeneratedSQL` is valid, plus every
`ValidationIssue` (error or warning) found, produced by
`sql_validation.SQLValidationEngine.validate`. Always produced —
validation never raises for invalid SQL.

**SQLRepairResult** — The outcome of a bounded repair loop over invalid
SQL, produced by `sql_repair.SQLRepairEngine.repair`: the original SQL
(unmodified), the final SQL artifact, the final SQL's own
`SQLValidationResult`, the complete attempt history, and a `RepairStatus`
(`REPAIRED` / `MAX_ATTEMPTS_REACHED` / `NO_PROGRESS` / `UNREPAIRABLE`).
Only produced when validation reported the original SQL invalid.

**SQLExecutionResult** — The outcome of running SQL against the real
database, produced by `sql_execution.SQLExecutionEngine.execute`: a
`status` (`SUCCESS`/`FAILED`/`REJECTED`/`TIMEOUT`), the raw
`QueryResult` (columns and rows exactly as the database returned them) on
success, and a structured `ExecutionError` otherwise. Never raises for an
ordinary execution failure.

**BusinessAnswer** — The final, presentable answer, produced by
`result_formatter.ResultFormatterEngine.format`: an `AnswerType`
classification, a deterministic `AnswerSummary`, a `FormattedTable` of
locale-independent rendered values, and `AnswerStatistics`. Only produced
from a *successful* `SQLExecutionResult`.

**QueryMindResponse** — The terminal model of the entire system, produced
by `orchestrator.QueryMindEngine.ask`: the original question, the
`BusinessAnswer` (on success), every intermediate phase artifact
(`generated_sql`, `validation_result`, `repair_result`,
`execution_result`), `PipelineStatistics`, an overall `status`, and an
`error` message on failure. `QueryMindEngine.ask` never raises — this
model is always what's returned.

## Cross-cutting concepts

**AnswerType** — The shape classification `result_formatter` assigns to a
`BusinessAnswer`: `SCALAR` (one row, one column), `TABLE` (many rows),
`EMPTY_RESULT` (zero rows), `AGGREGATION` (the executed SQL contains an
aggregate function or `GROUP BY`), or `DETAIL` (one row, multiple
columns).

**Ambiguity** — A business concept `schema_linker` could not resolve to
exactly one schema object unambiguously — recorded explicitly on
`LinkedQueryContext` rather than silently guessed.

**AsyncEngine / AsyncConnection** — SQLAlchemy's async engine and
connection types. The application constructs exactly one `AsyncEngine`
(`db.engine.create_engine`); `sql_execution.DatabaseConnectionProvider` is
the only component that checks out connections from it for pipeline use,
always tagged read-only.

**Business concept** — A business-domain term (`"customer"`, `"revenue"`,
`"AOV"`) as it appears in a question — a name, not yet resolved to a
column. Distinguished throughout the codebase from a *resolved* schema
object (a `ResolvedTable`/`ResolvedColumn`/`ResolvedMetric`).

**DatabaseConnectionProvider** — `sql_execution`'s component responsible
for acquiring and releasing read-only database connections from the
existing `AsyncEngine`. Never constructs its own engine.

**ExecutionGuard** — `sql_execution`'s final, independent safety gate: an
AST-level check (via `sqlglot`) that the SQL about to run is a single,
genuinely read-only `SELECT`/`WITH ... SELECT` statement, run in addition
to — not instead of — `SQLValidationResult.is_valid`.

**GenerationMetrics** — Observability data about one `LLMAdapter.generate`
call (provider, model, latency, token usage, retry count, finish reason),
embedded unmodified inside `GeneratedSQL.llm_metrics`.

**MetadataRegistry** — The single source of truth for database schema
structure plus business dictionary data (`metadata` package). Every
pipeline phase that needs schema information consumes this, never
`querymind.models` (the SQLAlchemy ORM) or a live connection directly.

**PipelineStage** — One of the eleven independently timed stages of the
end-to-end pipeline (`NLU`, `SCHEMA_LINKING`, `BUSINESS_KNOWLEDGE`,
`RETRIEVAL`, `PROMPT_COMPILATION`, `LLM`, `SQL_GENERATION`,
`SQL_VALIDATION`, `SQL_REPAIR`, `SQL_EXECUTION`, `RESULT_FORMATTING`),
defined in `orchestrator.models`. `SQL_REPAIR` is the only stage that
doesn't always run.

**PipelineExecutionError** — Raised by `orchestrator.PipelineRunner.run`
when any stage's own call genuinely raises (not for a "soft" failure
already expressed by a phase's own result type). Carries every artifact
and `StageTiming` produced before the failure; caught by
`QueryMindEngine.ask` and converted into a `FAILED` `QueryMindResponse`.

**QueryColumn / QueryRow** — `sql_execution`'s raw result-shape models:
one column's name/database type/Python type, and one row's tuple of raw
values, exactly as the database returned them. `QueryColumn` is reused
directly (not duplicated) as `FormattedTable.columns` in
`result_formatter`.

**RelationshipGraph** — The graph of foreign-key relationships between
tables, built by `MetadataRegistry.build_graph()`, consumed by
`schema_linker` (to connect resolved tables) and `sql_validation`'s join
validator (to confirm a join path is real).

**RepairStatus** — The outcome of one `SQLRepairEngine.repair` call:
`REPAIRED` (fully valid), `MAX_ATTEMPTS_REACHED`, `NO_PROGRESS` (an
attempt produced no improvement), or `UNREPAIRABLE`.

**StageTiming** — One `PipelineStage` plus how long it took, in
isolation. `PipelineStatistics.stage_timings` holds one per stage that
actually completed.

**ValidationIssue** — One structured finding from `sql_validation` — a
code, a `ValidationSeverity` (`ERROR`/`WARNING`), and a message. A
`SQLValidationResult` is invalid if and only if it has at least one
`ERROR`-severity issue.

**ValueFormatter** — `result_formatter`'s deterministic, locale-independent
single-value renderer (int/float/Decimal/bool/str/date/datetime/None →
text), with no rounding, no localization, and no currency inference.
