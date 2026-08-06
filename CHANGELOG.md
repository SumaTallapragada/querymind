# Changelog

All notable changes to QueryMind are documented in this file. Versions
correspond to development phases, not incremental releases — see
[`VERSION_HISTORY.md`](VERSION_HISTORY.md) for the full phase-by-phase
narrative and [`docs/pipeline.md`](docs/pipeline.md) for what each phase
implements.

## [1.0.0] — QueryMind Core Engine

The complete natural-language-question-to-`BusinessAnswer` pipeline,
feature-complete through Phase 15, stabilized and documented for release
in Phase 15.5.

### Completed phases

- **Phase 1** — Application foundation: FastAPI, async SQLAlchemy,
  structured logging, health endpoints, Docker.
- **Phases 2–4B** — 14-table domain schema, Alembic migrations, the
  Metadata Engine (`metadata`), and a synthetic data generation framework
  (`seeds`) with a CLI entry point (`scripts/seed_database.py`).
- **Phase 5** — NLU Engine (`nlu`): deterministic question parsing.
- **Phase 6** — Semantic Schema Linker (`schema_linker`): business
  concepts resolved to real schema objects.
- **Phase 7** — Business Knowledge Engine (`business_knowledge`):
  YAML-sourced business terminology catalog.
- **Phase 8** — Query Intelligence Library (`query_library`): curated
  gold-standard question-to-SQL examples.
- **Phase 9** — Knowledge Retrieval Engine (`retrieval`): explainable,
  eight-signal example ranking.
- **Phase 10A** — Prompt Compiler (`prompt_compiler`): token-budgeted,
  section-based prompt assembly.
- **Phase 10B** — LLM Adapter (`llm`): provider-agnostic Claude
  integration, the only network-calling component.
- **Phase 11A** — SQL Generation Engine (`sql_generation`): LLM response
  to normalized `GeneratedSQL`.
- **Phase 11B** — SQL Validation Engine (`sql_validation`): ten
  independent, read-only, `sqlglot`-based validators.
- **Phase 12** — SQL Repair Engine (`sql_repair`): bounded, automatic
  repair of invalid SQL.
- **Phase 13** — SQL Execution Engine (`sql_execution`): defense-in-depth
  read-only execution against the real database.
- **Phase 14** — Result Formatter / Answer Generator (`result_formatter`):
  deterministic `BusinessAnswer` construction.
- **Phase 15** — End-to-End QueryMind Orchestrator (`orchestrator`): the
  composition root, `QueryMindEngine.ask()`.
- **Phase 15.5** — Stabilization & release readiness: repository cleanup,
  documentation audit, public API audit, architecture audit, dependency
  audit, performance baseline, test suite audit, and this changelog/release
  preparation (this release).

### Architecture milestones

- A strict, one-directional 14-package dependency graph (`metadata` →
  `nlu` → `schema_linker` → `business_knowledge` → `query_library` →
  `retrieval` → `prompt_compiler` → `llm` → `sql_generation` →
  `sql_validation` → `sql_repair` → `sql_execution` → `result_formatter`
  → `orchestrator`), verified programmatically to have zero
  dependency-direction violations and zero circular imports.
- Every cross-phase model is an immutable Pydantic v2 model
  (`frozen=True`, `extra="forbid"`, tuples only).
- Constructor dependency injection throughout — no global state, no
  singleton services (`core.config.get_settings`'s narrowly scoped
  `lru_cache` aside).
- Two independent, defense-in-depth read-only guards on SQL execution
  (an AST-level `ExecutionGuard` plus a database-level read-only
  transaction).
- 1,068 tests passing, 78% statement coverage, real PostgreSQL used for
  every database-touching test, `httpx.MockTransport` for every
  LLM-touching test — no test suite run requires a live network call or
  API key.

### Notable design decisions

See [`docs/architecture-decisions.md`](docs/architecture-decisions.md)
for the full set of ADRs. Highlights: `sqlglot` (never regex) for every
structural SQL check; the LLM Adapter as the sole network-calling
component in the entire pipeline; SQL repair kept strictly separate from
(and re-using) SQL validation; SQL execution kept strictly separate from
result formatting, with a "soft failure" (`SQLExecutionResult.status !=
SUCCESS`) short-circuiting before the formatter is ever called.

### Breaking changes

None — this is the first tagged release.

### Current limitations

See [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) for the
complete list (PostgreSQL only, Claude only, no REST API, no streaming,
no auth, and others).

### Fixed in 15.5 (documentation/metadata only — no behavior change)

- `seeds/__init__.py`'s package docstring incorrectly stated that no data
  is generated or persisted and that persistence was future work; updated
  to describe what the package has actually done since Phase 4B.
- `pyproject.toml`'s `description` field still described the repository
  as "Phase 1: application foundation"; updated to describe the complete
  engine.
- Two stale-anchor cross-references within `docs/architecture-decisions.md`
  were corrected after that file's "Known gap" section was expanded (see
  below).

### Findings documented, not fixed, in 15.5

Per this phase's explicit "document, don't redesign" rule — see
[`docs/architecture-decisions.md`](docs/architecture-decisions.md#known-gaps)
for full detail:

- `metadata.RelationshipGraph.find_related_tables`/`.shortest_path`/
  `.find_join_path` are public, exported, fully documented methods that
  unconditionally raise `NotImplementedError`; no phase ever implements or
  calls them, and `schema_linker`/`sql_validation` each independently
  built their own equivalent traversal logic instead.
- `sql_repair.prompt_builder` depends on five `prompt_compiler` names
  (`estimate_tokens`, `CONSTRAINT_RULES`, and three section-builder
  classes) that are not part of `prompt_compiler.__all__` — a functionally
  necessary but currently undeclared cross-package dependency.
