# QueryMind System Design

This document describes the complete QueryMind engine as implemented: the
full pipeline, every model that flows between phases, and why each phase
exists as its own, separate component rather than being folded into its
neighbor.

## Complete pipeline

```
Natural Language Question
        │
        ▼
       NLU                     querymind.nlu.QueryParser.parse
        │
        ▼
  Schema Linking                querymind.schema_linker.SchemaLinker.link
        │
        ▼
 Business Knowledge              querymind.business_knowledge.BusinessKnowledgeRegistry.load
        │                        (consumed by Retrieval and SQL Validation)
        ▼
     Retrieval                  querymind.retrieval.RetrievalEngine.retrieve
        │
        ▼
 Prompt Compilation               querymind.prompt_compiler.PromptCompiler.compile
        │
        ▼
       LLM                      querymind.llm.LLMAdapter.generate
        │                        (invoked inside SQL Generation, not a separate call)
        ▼
  SQL Generation                 querymind.sql_generation.SQLGenerationEngine.generate
        │
        ▼
  SQL Validation                 querymind.sql_validation.SQLValidationEngine.validate
        │
        ├─ valid ────────────────────────────┐
        │                                    │
        ▼ invalid                            │
   SQL Repair                                 │
   querymind.sql_repair.SQLRepairEngine.repair │
        │                                    │
        └──────────────┬─────────────────────┘
                        ▼
                 SQL Execution              querymind.sql_execution.SQLExecutionEngine.execute
                        │
                        ▼
                Result Formatting            querymind.result_formatter.ResultFormatterEngine.format
                        │
                        ▼
                  BusinessAnswer
```

The whole sequence is driven by
`querymind.orchestrator.pipeline.PipelineRunner.run`, wrapped by
`querymind.orchestrator.engine.QueryMindEngine.ask` for a guaranteed
non-raising public entry point. See
[`ARCHITECTURE.md`](ARCHITECTURE.md#16-orchestration-flow) for the control
flow diagram.

## Models that flow between phases

Every model below is an immutable Pydantic v2 model (`frozen=True`,
`extra="forbid"`, tuples for every collection). Each is produced by
exactly one phase and consumed, unmodified, by the next.

### `QueryContext` — produced by NLU (`querymind.nlu.models`)

The structured interpretation of the raw question: `intent` (e.g.
`TOP_N`, `AGGREGATE`, `COMPARISON`), `primary_entity`/`secondary_entities`
(business concept *names*, e.g. `"customer"` — not yet resolved to a
table), `metrics`, `filters`, a `time_expression`, a `sort_expression`, and
a `limit_expression`. Nothing here has touched the database — every field
is derived purely from the question text.

### `LinkedQueryContext` — produced by Schema Linking (`querymind.schema_linker.models`)

`QueryContext`'s business-concept names resolved against the real schema,
via `querymind.metadata.MetadataRegistry`: `primary_entity`/
`secondary_entities` become `ResolvedTable`s (carrying the real
`TableMetadata`), `metrics` become `ResolvedMetric`s (a real
`ColumnMetadata` plus an aggregation function), `dimensions` become
`ResolvedColumn`s, and any concept that could not be resolved
unambiguously is recorded as an `Ambiguity` rather than silently guessed.

### `RetrievedKnowledgeBundle` — produced by Retrieval (`querymind.retrieval.models`)

Wraps the `LinkedQueryContext` plus the top-K most relevant
`RetrievedExample`s from the `querymind.query_library` catalog, each with
a full `SignalBreakdown` (per-signal score, weight, and a human-readable
explanation) and overall `RetrievalStatistics`. This is the last model
that carries retrieval-time context — the prompt compiler consumes it and
produces plain text.

### `CompiledPrompt` — produced by Prompt Compilation (`querymind.prompt_compiler.models`)

Seven independently built, immutable sections (`SystemSection`,
`BusinessSection`, `SchemaSection`, `RelationshipSection`,
`ExampleSection`, `ConstraintSection`, `OutputSection`), the exact
`PromptTemplate` used to assemble them, and `PromptStatistics`
(token estimates, trim decisions). `.as_text()` renders the whole thing
into the single string actually sent to the LLM.

### `LLMResponse` — produced by the LLM Adapter (`querymind.llm.models`)

Raw `content` text plus `GenerationMetrics` (provider, model, latency,
token usage, retry count, finish reason) — produced by
`LLMAdapter.generate`, called internally by `SQLGenerationEngine`, not
directly by the orchestrator.

### `GeneratedSQL` — produced by SQL Generation (`querymind.sql_generation.models`)

The final, normalized SQL text (`sql`), its detected `statement_type`, the
unmodified `raw_llm_content` it was extracted from, the target `dialect`,
the underlying `LLMResponse`'s own `GenerationMetrics` (`llm_metrics` —
this is where the orchestrator reads the LLM stage's independent timing
from), and `SQLGenerationStatistics` (extraction method, whether
normalization changed anything).

### `SQLValidationResult` — produced by SQL Validation (`querymind.sql_validation.models`)

`generated_sql` (unmodified), `is_valid`, `errors`/`warnings` (each a
`ValidationIssue` with a code, severity, and message), which
tables/columns/functions were actually validated, and
`ValidationStatistics` including a per-validator execution-time breakdown.
Always produced — validation never raises for invalid SQL.

### `SQLRepairResult` — produced by SQL Repair (`querymind.sql_repair.models`), when repair ran

`original_sql` (unmodified), `final_sql` (the last SQL artifact produced —
repaired if any attempt ran), `final_validation_result` (the validation
result *for* `final_sql`, reused directly by the orchestrator, never
re-validated manually), the complete `RepairHistory` (every attempt, in
order, nothing overwritten), `RepairStatistics`, and a `RepairStatus`
(`REPAIRED` / `MAX_ATTEMPTS_REACHED` / `NO_PROGRESS` / `UNREPAIRABLE`).

### `SQLExecutionResult` — produced by SQL Execution (`querymind.sql_execution.models`)

`status` (`SUCCESS`/`FAILED`/`REJECTED`/`TIMEOUT`), the `executed_sql`
text, `query_result` (a `QueryResult` — `QueryColumn`s plus `QueryRow`s of
raw values, populated only on `SUCCESS`), `ExecutionStatistics`
(latency, row/column counts, database name, dialect), and an
`execution_error` (populated only when not `SUCCESS`). Rows are the
database's own values, completely unmodified.

### `BusinessAnswer` — produced by Result Formatting (`querymind.result_formatter.models`)

`answer_type` (`SCALAR`/`TABLE`/`EMPTY_RESULT`/`AGGREGATION`/`DETAIL`), an
`AnswerSummary` (title, description, row/column counts, whether the result
contains numeric/date columns — built only from the result's own shape),
a `FormattedTable` (columns reused directly from `sql_execution.QueryColumn`;
rows of `FormattedValue`s, each carrying the original value, a
deterministic text rendering, and its detected type), `AnswerStatistics`,
and the originating `execution_result` for traceability.

### `QueryMindResponse` — produced by the Orchestrator (`querymind.orchestrator.models`)

The terminal model of the whole system: `original_question`, the
`business_answer` (only on success), `generated_sql`/`validation_result`
(always describing the SQL ultimately executed — the repaired SQL and its
own validation result, if repair ran), `repair_result` (`None` if repair
never ran), `execution_result`, `PipelineStatistics` (`total_latency_ms`,
one `StageTiming` per stage that actually completed, `repair_attempted`,
`repair_performed`), a `status` (`SUCCESS`/`FAILED`), and `error` (only on
failure).

### `GeneratedSqlResult` — produced by `QueryMindEngine.ask_for_sql` (`querymind.orchestrator.models`), added Phase 16

The same NLU-through-conditional-repair sequence as `QueryMindResponse`,
stopping before SQL Execution and Result Formatting: `original_question`,
`generated_sql`, `validation_result`, `repair_result` (`None` if repair
never ran), and `PipelineStatistics`. Added specifically to back the `POST
/query/sql` HTTP endpoint (see
[`ARCHITECTURE.md` §17](ARCHITECTURE.md#17-http-presentation-layer-phase-16)),
which must never execute SQL — unlike `QueryMindResponse`, there is no
`status`/`error` pair, since a genuine failure at any stage still
propagates as `PipelineExecutionError` rather than being represented as a
soft-failure field.

## How the HTTP API exposes these models

`querymind.api` (Phase 16) does not introduce a second set of response
models: every route above returns one of the models in this document
directly, serialized by Pydantic/FastAPI exactly as constructed by the
engine that produced it — `POST /query` returns a `QueryMindResponse`,
`POST /query/sql` a `GeneratedSqlResult`, `POST /query/validate` a
`SQLValidationResult`, and so on. See the [README](README.md#http-api) for
the full endpoint table and a worked request/response example, and
[`ARCHITECTURE.md` §17](ARCHITECTURE.md#17-http-presentation-layer-phase-16)
for how the presentation layer is wired.

## How streaming reports progress through these models (Phase 17)

`querymind.streaming` doesn't introduce a second pipeline or a second
set of *result* models either — every value in this document above is
still produced by exactly the engine that always produced it, in
exactly the same sequence. What Phase 17 adds is one new model,
`PipelineEvent` (`querymind.streaming.models`, nine subclasses — see
[`ARCHITECTURE.md` §18](ARCHITECTURE.md#18-streaming-phase-17)), that
reports *when* each of the transformations above starts and finishes,
in real time, as `PipelineRunner.run` executes:

```
pipeline_started
  -> stage_started(nlu)      -> stage_completed(nlu)          [QueryContext produced]
  -> stage_started(schema_linking) -> stage_completed(...)    [LinkedQueryContext produced]
  -> ... one started/completed pair per remaining stage ...
  -> stage_started(sql_execution)  -> stage_completed(...)    [SQLExecutionResult produced]
  -> stage_started(result_formatting) -> stage_completed(...) [BusinessAnswer produced]
-> pipeline_completed                                         [QueryMindResponse — carries the
                                                                 same BusinessAnswer, embedded
                                                                 in payload.business_answer]
```

A `stage_failed` event (instead of that stage's own `stage_completed`)
plus a final `pipeline_failed` event replace the above whenever a stage's
own call raises — the same `PipelineExecutionError` conversion
`QueryMindEngine.ask` always performed (see
[§16](ARCHITECTURE.md#16-orchestration-flow) above) still happens
identically; streaming only adds visibility into it, never a different
outcome. `PipelineCompletedEvent`'s `payload.business_answer` is the
exact same `BusinessAnswer` (`.model_dump(mode="json")`) `POST /query`
would have returned in its own `business_answer` field for the identical
question — see the [README](README.md#streaming-sse--websockets) for the
endpoint table and worked SSE/WebSocket examples.

## How authentication relates to these models (Phase 22A)

It doesn't, by design. `querymind.auth`'s models (`UserCreate`, `UserLogin`, `UserRead`,
`TokenPair`, `RefreshRequest` — `querymind.auth.schemas`) never enter the pipeline above at all:
nothing in `QueryContext -> ... -> QueryMindResponse` carries a user, and no pipeline model
carries auth data either. Authentication is a parallel concern sitting in front of the same
`/api/v1/*` routes, not another stage the question passes through — see
[`ARCHITECTURE.md` §19](ARCHITECTURE.md#19-authentication-phase-22a) for how it's wired. The one
place the two layers meet at all is `GET /api/v1/auth/me`, which returns a `UserRead` the exact
same way every other route returns its own model: constructed by the engine (here,
`AuthenticationService`) that owns it, serialized as-is.

## Why each phase exists

**NLU exists** because turning free text into structured intent (what kind
of question is this — a ranking, an aggregate, a comparison?) is a
different problem from mapping business words onto a schema, and solving
it with cheap, deterministic rules (no embeddings, no LLM) keeps the whole
first stage of the pipeline fast, free, and fully explainable.

**Schema Linking exists** separately from NLU because "what does
`'customer'` mean in this question" (NLU's job) and "what does `'customer'`
map to in *this specific database*" (schema linking's job) are genuinely
different questions — the first is about language, the second is about a
live, changeable schema. Keeping them separate means the schema can change
without touching a single line of NLU logic.

**Business Knowledge exists** as its own catalog, separate from the
schema, because business terms ("AOV", "Top Customer") often don't map to
a single column — they map to a *computation* over several columns, plus a
human-readable definition. Centralizing that in one YAML-sourced catalog
means both retrieval (to canonicalize terms) and validation (to enforce
business rules) consume the exact same definitions, never two competing
copies.

**The Query Intelligence Library exists** because good few-shot examples
measurably improve LLM SQL generation, and a curated, hand-verified example
set beats letting the LLM invent its own patterns from scratch — but the
library itself doesn't know how to *rank* examples for a specific
question; that's Retrieval's job.

**Retrieval exists** separately from the library because ranking (which
examples are most relevant *right now*) is a different, per-question
computation from storage (what examples exist at all) — and because
keeping ranking deterministic and explainable (eight scored signals, not a
black-box embedding similarity) means a wrong SQL generation can always be
traced back to *why* a particular example was retrieved.

**Prompt Compilation exists** separately from both retrieval and the LLM
adapter because assembling readable, token-budgeted prompt text from
structured data is its own non-trivial concern (section ordering, trimming
under a token budget, validating the result) that has nothing to do with
either ranking examples or calling a model — and because a different
prompt template or a different LLM provider should each be swappable
without touching the other.

**The LLM Adapter exists** as an isolated package specifically so it is
the *only* place in the entire codebase that makes a network call — every
other phase, including the ones that trigger it indirectly (SQL
Generation, SQL Repair), is fully testable with no network and no mocking
beyond swapping this one adapter's transport.

**SQL Generation exists** separately from the LLM Adapter because turning
a raw LLM response into usable SQL (extracting it from markdown fencing,
normalizing whitespace, detecting the statement type) is extraction logic,
not networking — and because this is the seam where a different
extraction/normalization strategy could be swapped in without touching how
the model itself is called.

**SQL Validation exists** as a strictly read-only phase, separate from
repair, because validation must be safe to call as many times as needed
(including by the repair loop, to re-check its own output) without ever
risking a side effect — and because ten independent, single-purpose
validators are each individually easier to reason about, test, and extend
than one large validation function.

**SQL Repair exists** separately from validation because *fixing* invalid
SQL requires a different tool (another LLM round trip) than *detecting*
that it's invalid — and bounding that round trip to a fixed number of
attempts, with a full history preserved, keeps a stubborn failure from
looping forever or silently vanishing.

**SQL Execution exists** as its own phase, strictly after validation and
repair, because running SQL against a real database is the one
irreversible-adjacent action in the whole pipeline (even read-only, it
costs real database resources and can leak schema/data details on
failure) — isolating it behind two independent read-only guards (AST-level
and database-level) means a bug anywhere upstream can never turn into a
write.

**Result Formatting exists** separately from execution because converting
raw database rows into a presentable answer is a formatting concern, not
a data-access concern — and keeping it strictly non-interpretive (no
invented business meaning, no charts) leaves room for a future phase to
add genuine business narration on top without this phase needing to
change.

**The Orchestrator exists** because every phase above is deliberately
unaware of its neighbors beyond the one model it consumes and the one it
produces — something has to own the actual sequence, the one conditional
branch (repair), and the guarantee that a caller always gets back a
structured response, never an unhandled exception. Putting that in its own
package, rather than in any one phase, keeps every phase substitutable
without the orchestrator's own logic changing.
