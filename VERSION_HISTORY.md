# Version History

**Current version: 1.0.0 — QueryMind Core Engine**

QueryMind was built incrementally, one phase at a time, each phase
consuming only the previous phases' public APIs and never redesigning
what came before. This document narrates that evolution. For what each
phase actually implements, see [`docs/pipeline.md`](docs/pipeline.md); for
the architectural reasoning behind it, see
[`docs/architecture-decisions.md`](docs/architecture-decisions.md).

## 1.0.0 — QueryMind Core Engine (Phases 1–15.5)

The complete natural-language-question-to-`BusinessAnswer` pipeline,
stabilized and documented for release.

**Foundation (Phases 1–4B).** Phase 1 established the application
skeleton: FastAPI, async SQLAlchemy, environment-driven configuration,
structured logging, health endpoints, and the Docker/tooling baseline
every later phase builds on unchanged. Phases 2 through 4B introduced the
14-table domain schema, Alembic migrations, the Metadata Engine (the
single source of truth for schema structure every later phase queries
instead of touching `querymind.models` directly), and a full synthetic
data generation framework. Phase 4B.1 was a small follow-up fix for a
SQLAlchemy warning surfaced during seed generation.

**The text-to-SQL pipeline (Phases 5–14).** Built strictly in pipeline
order, each phase deliberately stopping short of the next one's job: NLU
(5) parses a question into structured intent without touching the
database; Schema Linking (6) resolves that structure against the real
schema; Business Knowledge (7) and the Query Intelligence Library (8)
built the two knowledge bases Retrieval (9) ranks examples against;
Prompt Compilation (10A) and the LLM Adapter (10B) were split specifically
so exactly one component in the whole system makes a network call; SQL
Generation (11A) and SQL Validation (11B) turn that LLM response into
checked SQL; SQL Repair (12) closes the loop on invalid SQL without ever
touching the validation logic that flagged it; SQL Execution (13) is the
one phase that runs anything against the real database, behind two
independent read-only guards; Result Formatting (14) turns a successful
execution into a presentable, non-interpretive answer.

**Orchestration (Phase 15).** `QueryMindEngine`/`PipelineRunner` composed
all fourteen prior packages into one sequential, fully-timed,
never-raising call — the first phase permitted to import broadly across
the whole domain-engine layer, since composing them is exactly its job.

**Stabilization (Phase 15.5).** A repository-hardening pass, not a
feature phase: cleanup (one stale docstring corrected), a full
documentation audit (zero broken links/anchors found), a public API audit
across all 14 packages (two real cross-package boundary issues found and
documented, not fixed), an architecture audit (dependency direction and
circular-import checks run programmatically, zero violations), a
dependency audit, a real measured performance baseline, a test-suite
audit, and this changelog/versioning/known-limitations documentation set
— preparing the engine as a v1.0 release candidate.

## Pre-1.0 development phases

| Phase | Delivered |
|---|---|
| 1 | Application foundation (FastAPI, async SQLAlchemy, config, logging, health checks, Docker) |
| 2–4B | Domain schema (14 tables), Metadata Engine, synthetic data generation framework |
| 5 | NLU Engine (`nlu`) |
| 6 | Semantic Schema Linker (`schema_linker`) |
| 7 | Business Knowledge Engine (`business_knowledge`) |
| 8 | Query Intelligence Library (`query_library`) |
| 9 | Knowledge Retrieval Engine (`retrieval`) |
| 10A | Prompt Compiler (`prompt_compiler`) |
| 10B | LLM Adapter (`llm`) |
| 11A | SQL Generation Engine (`sql_generation`) |
| 11B | SQL Validation Engine (`sql_validation`) |
| 12 | SQL Repair Engine (`sql_repair`) |
| 13 | SQL Execution Engine (`sql_execution`) |
| 14 | Result Formatter / Answer Generator (`result_formatter`) |
| 15 | End-to-End QueryMind Orchestrator (`orchestrator`) |
| 15.5 | Stabilization & release readiness (this release) |

## What's next

Phase 16 (FastAPI Service Layer — exposing `QueryMindEngine` over HTTP)
is the next planned phase and is explicitly **not** part of this release.
See [`README.md`'s roadmap](README.md#project-roadmap) and
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) for the complete
list of what v1.0 does not yet include.
