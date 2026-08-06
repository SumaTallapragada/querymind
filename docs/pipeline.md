# Pipeline: Phase by Phase

QueryMind was built incrementally, one phase per commit, each phase
consuming only the previous phases' public APIs. This document describes
every phase from the application foundation through the end-to-end
orchestrator, in the order they were built.

## Phase 1 — Application foundation

**Package:** `core`, `db`, `api`, `main.py`

A running FastAPI service with async PostgreSQL connectivity
(SQLAlchemy 2.0 + asyncpg), environment-driven configuration
(`pydantic-settings`, no hardcoded values), structured `structlog`
logging with per-request correlation IDs, liveness/readiness health
endpoints, Alembic wired for async migrations, and a multi-stage
Dockerfile. No AI pipeline or business domain models exist at this phase
— it is pure infrastructure that every later phase builds on without
restructuring.

## Phases 2–4B — Schema, metadata layer, business simulation

**Packages:** `models`, `metadata`, `seeds`

Introduces the 14-table domain schema (`models/`) — customers, orders,
payments, products, suppliers, inventory, warehouses, shipments,
promotions, reviews, returns — with Alembic migrations. `metadata/` builds
the `MetadataRegistry`: the single source of truth for schema structure
plus a business-friendly column dictionary, consumed by every later phase
that needs to know "what does the database look like" without importing
SQLAlchemy models directly. `seeds/` implements a full synthetic
data-generation framework — one generator per table, business-consistency
rules, and an orchestrator that persists everything in dependency order
through `scripts/seed_database.py` (see
[`getting-started.md`](getting-started.md#4-seed-the-database)). Phase
4B.1 was a follow-up fix for a SQLAlchemy warning surfaced during seed
generation.

## Phase 5 — NLU Engine

**Package:** `nlu` · **Entry point:** `QueryParser.parse(question: str) -> QueryContext`

Turns a natural language question into a structured `QueryContext` using
only deterministic techniques — regex, keyword matching, rule-based
parsing, a fixed business vocabulary. No embeddings, no vector search, no
LLM call. Extracts `intent` (e.g. `TOP_N`, `AGGREGATE`), `primary_entity`/
`secondary_entities`/`business_concepts` (canonical business-concept
*names*, not yet resolved to real tables), `metrics`, `filters`, a
`time_expression`, a `sort_expression`, and a `limit_expression`.
Deliberately stops short of resolving anything against the real schema —
that is schema linking's job.

## Phase 6 — Semantic Schema Linker

**Package:** `schema_linker` · **Entry point:** `SchemaLinker.link(query_context: QueryContext) -> LinkedQueryContext`

Maps `QueryContext`'s business-concept names onto the real database
schema, using `querymind.metadata.MetadataRegistry` and its
`RelationshipGraph` — never `querymind.models` or a live connection
directly. Matching is deterministic and prioritized: exact identifier
match, business dictionary lookup, declared synonyms, rule-based
alias/abbreviation expansion, `difflib` fuzzy similarity, then substring
containment. Never silently guesses — an ambiguous or unresolvable
concept is recorded as an explicit `Ambiguity` on the output, not an
automatic pick.

## Phase 7 — Business Knowledge Engine

**Package:** `business_knowledge` · **Entry point:** `BusinessKnowledgeRegistry` (`load()`, `get_concept()`, `find_concepts()`, `resolve()`)

Understands business terminology ("Revenue", "Top Customer", "AOV") and
maps it to business *semantics* — a `BusinessConcept` with a description,
a computation (`BusinessFormula`), and example questions — from a
deterministic, YAML-sourced catalog. Does not resolve concepts against the
schema (schema linking's job) and does not generate SQL. Matching order:
exact name, alias, synonym (via `related_terms`), substring containment.
Sits between NLU and Schema Linking conceptually, but in the actual
pipeline it is consumed directly by Retrieval (to canonicalize concept
terms before scoring) and by SQL Validation (to enforce business rules).

## Phase 8 — Query Intelligence Library

**Package:** `query_library` · **Entry point:** `QueryLibraryRegistry` (`load()`, `get_example()`, `find_examples()`, `search_by_*()`)

A curated, YAML-sourced catalog of hand-verified, gold-standard
natural-language-question-to-SQL examples covering every major schema area
and analytical pattern (financial metrics, time-based analysis, Top-N,
trend analysis, filtering, grouping, joins, aggregations). Plain,
deterministic data plus deterministic keyword search — no embeddings, no
vector database, no LLM, no execution. Ranking examples for a specific
question is Retrieval's job, not this package's.

## Phase 9 — Knowledge Retrieval Engine

**Package:** `retrieval` · **Entry point:** `RetrievalEngine.retrieve(linked_query_context, top_k=None) -> RetrievedKnowledgeBundle`

Ranks every example in the Query Intelligence Library against the current
`LinkedQueryContext` and returns the top-K, each with a full,
explainable `SignalBreakdown`. Consumes the Query Library (the candidate
pool), Business Knowledge (canonicalizing concept terms before comparing),
and the Schema Linker's own output (indirectly, the Metadata Engine's real
`TableMetadata`/`ColumnMetadata` already embedded in `LinkedQueryContext`).
Scoring is eight independent, deterministic signals (intent similarity,
business concept overlap, schema/table/column overlap, SQL feature
overlap, keyword overlap, difficulty similarity), combined by configurable
weights. Not a prompt builder and does not generate SQL.

## Phase 10A — Prompt Compiler

**Package:** `prompt_compiler` · **Entry point:** `PromptCompiler.compile(bundle, dialect=SQLDialect.POSTGRESQL) -> CompiledPrompt`

Converts a `RetrievedKnowledgeBundle` into a `CompiledPrompt`: seven
independently built sections (system, business context, schema context,
relationships, retrieved examples, constraints, output format), validated
and trimmed to fit a configurable token budget, assembled into one
immutable model with a `.as_text()` rendering. Not an LLM client — knows
nothing about any specific provider; that integration is Phase 10B.

## Phase 10B — LLM Adapter

**Package:** `llm` · **Entry point:** `LLMAdapter.generate(compiled_prompt: CompiledPrompt) -> LLMResponse`

A provider-agnostic bridge from a `CompiledPrompt` to an `LLMResponse`.
Handles retries (`RetryPolicy`), timeouts, and response parsing behind one
interface (`ProviderClient`); `ClaudeProvider` is the concrete
implementation, talking to the Anthropic Claude API over a raw `httpx`
client (no vendor SDK dependency). This is the **only** package in the
entire pipeline that makes a network call — every other phase is fully
testable without one. Knows nothing about SQL.

## Phase 11A — SQL Generation Engine

**Package:** `sql_generation` · **Entry point:** `SQLGenerationEngine.generate(compiled_prompt: CompiledPrompt) -> GeneratedSQL`

Converts a `CompiledPrompt` into a `GeneratedSQL` using the existing
`LLMAdapter` (called internally — this is the one place the LLM stage
actually executes in the full pipeline). Extracts SQL text from the raw
response, normalizes it cosmetically, detects the statement type, and
returns an immutable result carrying the LLM's own `GenerationMetrics` for
full traceability. Does not validate, execute, or repair SQL, and does not
modify the prompt.

## Phase 11B — SQL Validation Engine

**Package:** `sql_validation` · **Entry point:** `SQLValidationEngine.validate(generated_sql: GeneratedSQL) -> SQLValidationResult`

Validates `GeneratedSQL` before it may proceed to execution: parses it
with `sqlglot`, then runs ten independent, read-only validators against
the resulting AST plus the Metadata Engine, Relationship Graph, and
Business Knowledge Engine — syntax, schema, table, column, join, function,
aggregate, alias, business rule, dialect. Never modifies, repairs, or
optimizes SQL, and never executes it or calls an LLM. Always returns a
result — never raises for invalid SQL.

## Phase 12 — SQL Repair Engine

**Package:** `sql_repair` · **Entry point:** `SQLRepairEngine.repair(generated_sql, validation_result, bundle) -> SQLRepairResult`

Automatically repairs SQL that validation found invalid, reusing the
existing Prompt Compiler, LLM Adapter, and SQL Validation Engine over a
bounded, deterministic loop (`DEFAULT_MAX_ATTEMPTS` attempts, default 3).
Does not execute, optimize, or explain SQL. The original `GeneratedSQL` is
never mutated — every attempt produces a new artifact, and the complete
attempt history (`RepairHistory`) is always preserved, even for attempts
that didn't succeed.

## Phase 13 — SQL Execution Engine

**Package:** `sql_execution` · **Entry point:** `SQLExecutionEngine.execute(generated_sql, validation_result) -> SQLExecutionResult` (async)

Executes validated (or repaired) SQL read-only against the real database,
reusing the application's existing async SQLAlchemy engine — no second
engine, no ORM models, no writes. Read-only is enforced two independent
ways: an AST-level `ExecutionGuard` (rejecting anything but a single
`SELECT`/`WITH ... SELECT`, walking the whole tree to catch a write hidden
in a writable CTE) and a database-level read-only transaction
(`postgresql_readonly=True`). Does not generate, repair, optimize, or
explain SQL, and does not summarize results. `execute()` never raises for
an ordinary execution failure — every outcome is a structured
`SQLExecutionResult`.

## Phase 14 — Result Formatter / Answer Generator

**Package:** `result_formatter` · **Entry point:** `ResultFormatterEngine.format(execution_result: SQLExecutionResult) -> BusinessAnswer`

Turns a successful `SQLExecutionResult` into an immutable `BusinessAnswer`:
a formatted table (deterministic, locale-independent value formatting — no
rounding, no localization, no currency inference), a summary built only
from the result's own shape (row/column counts, column names — never
inferred business meaning), and an `AnswerType` classification
(`SCALAR`/`TABLE`/`EMPTY_RESULT`/`AGGREGATION`/`DETAIL`). Does not execute,
validate, generate, or repair SQL, does not call the LLM, and produces no
visualization (no HTML, no markdown tables, no charts, no CSV/Excel).

## Phase 15 — End-to-End QueryMind Orchestrator

**Package:** `orchestrator` · **Entry point:** `QueryMindEngine.ask(question: str) -> QueryMindResponse` (async)

The composition root: wires every phase above, through its own public
entry point, into `PipelineRunner`, which performs the exact sequence
(NLU → Schema Linking → Business Knowledge → Retrieval → Prompt
Compilation → SQL Generation [LLM inside] → SQL Validation → SQL Repair
*only if validation failed* → SQL Execution → Result Formatting) and
times every stage independently. `QueryMindEngine.ask` never raises — any
stage's own failure, or a "soft" failure already expressed by a phase's
own result type (e.g. `SQLExecutionResult.status != SUCCESS`), becomes a
structured `FAILED` `QueryMindResponse` instead. Orchestration only: no
SQL generation, validation, repair, formatting, prompt-building, retrieval,
or execution logic lives in this package. Does not expose REST, a CLI, or
a UI — see the [roadmap](../README.md#project-roadmap).

## Worked example

A real question, run through the real pipeline (real schema linking,
retrieval, and SQL validation against the project's own shipped schema; a
scripted LLM response in place of a live network call; real execution
against the seeded database):

**Question:** *"Who are our top 5 customers by revenue?"*

Generated and executed SQL:

```sql
SELECT c.customer_id, SUM(o.total_amount) AS total_revenue
FROM customers c JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 5;
```

Resulting `QueryMindResponse` (abbreviated):

```json
{
  "status": "success",
  "repair_result": null,
  "business_answer": {
    "answer_type": "aggregation",
    "summary": {"title": "Returned 5 rows.", "row_count": 5, "column_count": 2},
    "formatted_table": {
      "rows": [
        {"values": [{"formatted_value": "120"}, {"formatted_value": "32473.80"}]},
        {"values": [{"formatted_value": "951"}, {"formatted_value": "30677.77"}]},
        {"values": [{"formatted_value": "1395"}, {"formatted_value": "29819.20"}]},
        {"values": [{"formatted_value": "368"}, {"formatted_value": "29138.71"}]},
        {"values": [{"formatted_value": "175"}, {"formatted_value": "28496.20"}]}
      ]
    }
  },
  "statistics": {
    "total_latency_ms": 262.75,
    "repair_attempted": false,
    "repair_performed": false,
    "stage_timings": [
      {"stage": "nlu", "latency_ms": 11.09},
      {"stage": "schema_linking", "latency_ms": 36.34},
      {"stage": "business_knowledge", "latency_ms": 0.01},
      {"stage": "retrieval", "latency_ms": 12.28},
      {"stage": "prompt_compilation", "latency_ms": 1.74},
      {"stage": "sql_generation", "latency_ms": 1.84},
      {"stage": "llm", "latency_ms": 1.60},
      {"stage": "sql_validation", "latency_ms": 7.32},
      {"stage": "sql_execution", "latency_ms": 190.09},
      {"stage": "result_formatting", "latency_ms": 1.95}
    ]
  }
}
```

Ten of the eleven `PipelineStage` timings are present — `sql_repair` is
correctly absent, since the generated SQL validated successfully on the
first attempt. Revenue figures are real values from the seeded
`customers`/`orders` tables, not illustrative placeholders.
