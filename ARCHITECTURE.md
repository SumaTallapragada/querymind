# QueryMind Architecture

This document is the canonical architecture reference for QueryMind. It
describes what is actually implemented, not what any earlier specification
proposed — where the two differ, this document follows the code.

## 1. Overall architecture

QueryMind is a **pipeline of small, single-responsibility engines**, each
implemented as its own top-level package under `src/querymind/`, composed
by one orchestrator (`querymind.orchestrator`) into a single end-to-end
call. There is no shared mutable state between stages: each stage receives
an immutable input, produces a new immutable output, and never mutates
what it was given.

```mermaid
flowchart LR
    subgraph Foundation["Foundation (Phases 1-4B)"]
        CFG[core.config]
        DB[db]
        MDL[models — ORM]
        SEED[seeds]
    end

    subgraph Metadata["Schema knowledge (Phase 2-3)"]
        META[metadata]
    end

    subgraph Pipeline["Text-to-SQL pipeline (Phases 5-14)"]
        NLU[nlu]
        SL[schema_linker]
        BK[business_knowledge]
        QL[query_library]
        RET[retrieval]
        PC[prompt_compiler]
        LLM[llm]
        GEN[sql_generation]
        VAL[sql_validation]
        REP[sql_repair]
        EXEC[sql_execution]
        FMT[result_formatter]
    end

    subgraph Orchestration["Composition root (Phase 15)"]
        ORCH[orchestrator]
    end

    DB --> META
    MDL --> META
    META --> SL
    META --> VAL
    META --> REP
    NLU --> SL
    SL --> RET
    BK --> RET
    QL --> RET
    RET --> PC
    PC --> LLM
    LLM --> GEN
    GEN --> VAL
    VAL --> REP
    VAL --> EXEC
    REP --> EXEC
    DB --> EXEC
    EXEC --> FMT

    ORCH --> NLU
    ORCH --> SL
    ORCH --> BK
    ORCH --> RET
    ORCH --> PC
    ORCH --> GEN
    ORCH --> VAL
    ORCH --> REP
    ORCH --> EXEC
    ORCH --> FMT
```

`core`, `db`, `models`, and `metadata` are **infrastructure**, consumed
directly by multiple pipeline stages. `nlu` through `result_formatter` are
**domain engines**: each owns exactly one transformation, consumes only
the previous stage's output plus whatever infrastructure it genuinely
needs, and exposes exactly one public entry point (a `.parse()`, `.link()`,
`.retrieve()`, `.compile()`, `.generate()`, `.validate()`, `.repair()`,
`.execute()`, or `.format()` method on one class). `orchestrator` is the
**composition root**: the only package permitted to import and wire every
other pipeline package together.

## 2. Layered architecture

```mermaid
flowchart TB
    API["api / main.py\n(FastAPI presentation layer — Phase 1 only today)"]
    ORCH["orchestrator\n(composition root)"]
    DOMAIN["nlu · schema_linker · business_knowledge · query_library ·\nretrieval · prompt_compiler · llm · sql_generation ·\nsql_validation · sql_repair · sql_execution · result_formatter\n(domain engines)"]
    INFRA["metadata · db · models · seeds · core\n(infrastructure)"]

    API --> DOMAIN
    ORCH --> DOMAIN
    DOMAIN --> INFRA
```

Four layers, strictly downward-dependent:

1. **Presentation** (`api`, `main.py`) — today limited to Phase 1's health
   endpoints; does not yet call into the pipeline (see
   [roadmap](README.md#project-roadmap)).
2. **Composition root** (`orchestrator`) — the only package that imports
   more than one or two adjacent domain engines. It sequences calls; it
   contains no business logic of its own.
3. **Domain engines** (`nlu` through `result_formatter`) — each is
   self-contained, importing only the infrastructure layer and, at most,
   the specific upstream models it needs to consume (e.g.
   `sql_repair` imports `sql_validation.models.SQLValidationResult`, never
   `sql_validation`'s internal validator classes).
4. **Infrastructure** (`metadata`, `db`, `models`, `seeds`, `core`) — no
   dependency on any domain engine. `metadata` is the one piece of
   infrastructure most domain engines depend on directly: it is the single
   source of truth for "what does the database look like," so that no
   domain engine ever imports `querymind.models` (SQLAlchemy) or opens a
   database connection to answer a schema question.

## 3. Dependency direction

Dependencies point in one direction only: **presentation → orchestrator →
domain engines → infrastructure.** No package in a lower layer imports
from a higher one. Within the domain-engine layer, dependencies follow
pipeline order — a later phase may import an earlier phase's public models
(e.g. `sql_validation` imports `sql_generation.models.GeneratedSQL`), but
never the reverse, and never another phase's private (underscore-prefixed
or non-exported) implementation classes. Every phase's `__init__.py`
defines its complete public surface via `__all__`; nothing outside that
list is considered part of the package's contract.

`querymind.orchestrator` is the single exception permitted to import
across the whole domain-engine layer at once — that breadth is exactly
its job as the composition root.

## 4. Every package and its responsibility

| Package | Responsibility | Public entry point |
|---|---|---|
| `core` | Environment-driven `Settings`, structured logging setup | `Settings`, `configure_logging` |
| `db` | Async SQLAlchemy engine/session construction, declarative base | `create_engine`, `create_session_factory`, `Base` |
| `models` | SQLAlchemy ORM models for the 14-table domain schema | one module per table, all registered on `Base.metadata` |
| `seeds` | Synthetic, referentially valid dataset generation and persistence | `SeedOrchestrator`, `AsyncSessionTransactionRunner` |
| `metadata` | Single source of truth for schema structure + business dictionary | `MetadataRegistry` |
| `api` | FastAPI presentation layer (health checks today) | `api_router` |
| `nlu` | Deterministic parsing of a question into structured intent/entities | `QueryParser.parse` |
| `schema_linker` | Resolve business concept names onto real tables/columns | `SchemaLinker.link` |
| `business_knowledge` | Business terminology → business semantics (description, formula, examples) | `BusinessKnowledgeRegistry` |
| `query_library` | Curated gold-standard question→SQL example catalog | `QueryLibraryRegistry` |
| `retrieval` | Rank the most relevant few-shot examples for a linked question | `RetrievalEngine.retrieve` |
| `prompt_compiler` | Assemble a token-budgeted, validated LLM prompt | `PromptCompiler.compile` |
| `llm` | Provider-agnostic LLM call (retries, timeouts, parsing) | `LLMAdapter.generate` |
| `sql_generation` | Turn an LLM response into normalized `GeneratedSQL` | `SQLGenerationEngine.generate` |
| `sql_validation` | Ten independent read-only AST validators | `SQLValidationEngine.validate` |
| `sql_repair` | Bounded, automatic repair of invalid SQL via the LLM | `SQLRepairEngine.repair` |
| `sql_execution` | Read-only execution of validated SQL against the real database | `SQLExecutionEngine.execute` |
| `result_formatter` | Deterministic formatting of results into a `BusinessAnswer` | `ResultFormatterEngine.format` |
| `orchestrator` | Compose all of the above into one end-to-end call | `QueryMindEngine.ask` |

See [`docs/project-structure.md`](docs/project-structure.md) for a
file-by-file breakdown within each package.

## 5. Why immutable models are used

Every model that crosses a phase boundary — from `QueryContext` through
`QueryMindResponse` — is a Pydantic v2 model with `model_config =
ConfigDict(frozen=True, extra="forbid")`, and every collection field is a
`tuple`, never a `list`. This is enforced, not a convention left to
discipline: a `frozen=True` Pydantic model raises on attribute
reassignment, and a `tuple` (unlike a `list` field on a frozen model)
genuinely cannot be mutated in place.

This matters specifically because the pipeline is a **strict, one-directional
chain of transformations**: `sql_repair` receives the `GeneratedSQL` and
`SQLValidationResult` that `sql_validation` produced and must never be able
to alter what `sql_validation` reported, even accidentally — repair
attempts always construct a *new* `GeneratedSQL`, never edit the original
in place. `extra="forbid"` catches a second, different class of bug: a
typo'd or stale field name in a constructor call fails immediately at
model construction, not silently three phases later when some consumer
reads a field that was never actually set.

## 6. Dependency Injection strategy

Every engine and collaborator in this codebase is **constructor-injected**,
with no global state, no singleton services, and no service locator
anywhere in the pipeline (see
[`docs/architecture-decisions.md`](docs/architecture-decisions.md) for the
rationale). Two recurring patterns:

- **Sensible-default collaborators.** A class's fine-grained internal
  collaborators (e.g. `SchemaLinker`'s `ConceptResolver`,
  `PromptCompiler`'s seven section builders) are typed as
  `Collaborator | None = None` and default to the standard implementation
  when omitted, so ordinary callers don't need to wire seven objects by
  hand — but a test or an alternate composition can substitute any of them
  without modifying the class.
- **Required-and-only-injected external dependencies.** A class's
  dependency on something the class itself cannot sensibly construct (a
  `MetadataRegistry`, a `DatabaseConnectionProvider`, an `LLMAdapter`) is a
  required constructor parameter with no default. `PipelineRunner`
  (`querymind.orchestrator.pipeline`) is the clearest example: all ten of
  its collaborators are required, fully-constructed instances of each
  phase's own public entry point — the orchestrator builds none of them
  itself, since only the actual composition root (a script, or eventually
  an API startup handler) has the real configuration (credentials, an
  event loop, a live database) needed to construct them.

## 7. Validation strategy

`sql_validation.SQLValidationEngine` parses `GeneratedSQL.sql` once with
`sqlglot` and runs ten independent validators against the resulting AST,
each read-only and single-purpose: syntax, schema (do referenced
tables/columns exist), table, column, join (is the join path real, per the
metadata `RelationshipGraph`), function, aggregate, alias, business rule
(`business_knowledge`-sourced constraints), and dialect. `validate()` never
raises for invalid SQL — every outcome, valid or not, is a structured
`SQLValidationResult` with `is_valid` plus a list of `ValidationIssue`s.
Validation never modifies the SQL it inspects; repairing invalid SQL is
`sql_repair`'s job, not this package's.

## 8. Repair strategy

`sql_repair.SQLRepairEngine.repair` runs only when `SQLValidationResult.is_valid`
is `False`. It reuses the existing Prompt Compiler, LLM Adapter, and SQL
Validation Engine over a bounded, deterministic loop (`DEFAULT_MAX_ATTEMPTS`
attempts): build a repair-specific prompt containing the original SQL and
its exact validation errors, call the LLM, extract and re-validate the
result, and stop as soon as a fully valid SQL is produced or the attempt
budget is exhausted. Every attempt's input and output is preserved in an
immutable `RepairHistory` — nothing is overwritten, and the original
`GeneratedSQL` is never mutated. Repair is a distinct phase from
validation specifically so validation stays a pure, side-effect-free
read: `RepairValidator` wraps the same `SQLValidationEngine` repair uses to
re-check its own output, rather than repair re-implementing any validation
logic itself.

## 9. Prompt compilation strategy

`prompt_compiler.PromptCompiler.compile` builds a `CompiledPrompt` from
seven independently constructed sections (system, business context, schema
context, relationships, retrieved examples, constraints, output format),
each produced by its own section builder from the `RetrievedKnowledgeBundle`.
A `PromptBudgetManager` trims the non-required sections (in a fixed,
documented order) until the whole prompt fits a configurable token budget,
and a `PromptValidator` checks the final result before it is returned.
Prompt compilation never calls an LLM and never generates SQL — it produces
text, nothing more; `llm.LLMAdapter` is a completely separate package with
no knowledge of prompts, sections, or SQL.

## 10. Retrieval strategy

`retrieval.RetrievalEngine.retrieve` ranks every `QueryExample` in the
`QueryLibraryRegistry` against the current `LinkedQueryContext` using eight
independent, deterministic signals (intent similarity, business concept
overlap, schema/table/column overlap, SQL feature overlap, keyword
overlap, difficulty similarity), combines them with configurable weights,
and returns the top-K as a `RetrievedKnowledgeBundle` — each retrieved
example carries a full `SignalBreakdown` explaining exactly why it scored
the way it did. No embeddings, no vector search, no LLM call anywhere in
this package.

## 11. SQL generation flow

`sql_generation.SQLGenerationEngine.generate` is the one place the LLM is
actually invoked: it sends the `CompiledPrompt` to the injected
`LLMAdapter`, extracts SQL text from the raw response (`SQLExtractor`),
normalizes it cosmetically (`SQLNormalizer`), detects the statement type,
and returns an immutable `GeneratedSQL` carrying the LLM's own
`GenerationMetrics` (including its independently measured latency) for
full traceability. It performs no validation, no execution, and no repair.

## 12. SQL validation flow

See [§7](#7-validation-strategy) above; see
[`docs/architecture-decisions.md`](docs/architecture-decisions.md) for why
`sqlglot` specifically was chosen over regex-based checks.

## 13. SQL repair flow

See [§8](#8-repair-strategy) above.

## 14. SQL execution flow

`sql_execution.SQLExecutionEngine.execute` is read-only in two independent,
overlapping ways:

1. **AST-level guard.** `ExecutionGuard` re-parses the exact SQL text about
   to run (with `sqlglot.parse`, not `parse_one`, specifically to catch
   multi-statement smuggling) and rejects anything that is not a single
   `SELECT`/`WITH ... SELECT` statement, walking the entire AST — not just
   the root node — to catch a write hidden inside a writable CTE.
2. **Database-level guard.** `DatabaseConnectionProvider` opens every
   connection with `postgresql_readonly=True`, so even a write that
   somehow evaded the AST guard would still be rejected by PostgreSQL
   itself.

It reuses the application's existing async `SQLAlchemy` engine (never
constructing a second one), executes under a caller-configurable timeout,
and converts every failure mode (rejection, timeout, database error,
formatting error) into a structured `SQLExecutionResult` — `execute()`
never raises for an ordinary execution failure.

## 15. Result formatting flow

`result_formatter.ResultFormatterEngine.format` accepts only a successful
`SQLExecutionResult` and produces an immutable `BusinessAnswer`: a
formatted table (deterministic, locale-independent value rendering via
`ValueFormatter`), a summary built strictly from the result's own shape
(row/column counts, column names — never inferred business meaning), and
an `AnswerType` classification (`SCALAR`/`TABLE`/`EMPTY_RESULT`/
`AGGREGATION`/`DETAIL`) derived from row/column counts plus a read-only
`sqlglot` inspection of the already-executed SQL text for aggregate
functions or `GROUP BY`. It performs no business calculation and produces
no visualization.

## 16. Orchestration flow

```mermaid
sequenceDiagram
    participant Caller
    participant Engine as QueryMindEngine
    participant Runner as PipelineRunner
    participant Stages as NLU → ... → Result Formatting

    Caller->>Engine: ask(question)
    Engine->>Runner: run(question)
    Runner->>Stages: sequential calls, one StageTiming per completed stage
    alt every stage succeeds
        Stages-->>Runner: BusinessAnswer
        Runner-->>Engine: QueryMindResponse(status=SUCCESS)
    else a stage raises
        Stages-->>Runner: exception
        Runner-->>Engine: raises PipelineExecutionError (partial timings + artifacts)
        Engine-->>Engine: catch, build QueryMindResponse(status=FAILED)
    else execution succeeds but SQLExecutionResult.status != SUCCESS
        Stages-->>Runner: SQLExecutionResult(status=FAILED/REJECTED/TIMEOUT)
        Runner-->>Engine: QueryMindResponse(status=FAILED) — Result Formatter never called
    end
    Engine-->>Caller: QueryMindResponse (never raises)
```

`PipelineRunner.run` performs the exact sequence (NLU → Schema Linking →
Business Knowledge → Retrieval → Prompt Compilation → SQL Generation
[which internally calls the LLM] → SQL Validation → SQL Repair
*conditionally, only when validation failed* → SQL Execution → Result
Formatting), timing every stage independently and reusing `SQLRepairResult
.final_sql`/`.final_validation_result` directly rather than re-validating
repaired SQL manually. `QueryMindEngine.ask` wraps `PipelineRunner.run` and
guarantees it never raises: any stage's own exception becomes a
`PipelineExecutionError` carrying every artifact and timing produced
before the failure, which `QueryMindEngine` converts into a `FAILED`
`QueryMindResponse` rather than losing that partial progress.

See [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) for the complete model-by-model
walkthrough of what flows between every stage.
