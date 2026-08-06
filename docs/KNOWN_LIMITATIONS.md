# Known Limitations

This document lists what QueryMind Core Engine v1.0 does **not** do today.
Every item below reflects the actual current implementation, not a
prioritized roadmap — see
[`README.md`](../README.md#project-roadmap) for what's explicitly deferred
to future work, and [`docs/architecture-decisions.md`](architecture-decisions.md#known-gaps)
for specific internal gaps discovered during the Phase 15.5 audit.

## Database

**PostgreSQL only.** `sql_execution.DatabaseConnectionProvider` is built
directly on an async SQLAlchemy engine configured for
`postgresql+asyncpg`. `sql_validation`/`sql_repair`/`sql_execution` all
carry a `SQLDialect` field and *could* target another dialect at the
`sqlglot` parsing level, but nothing in this codebase has been built,
tested, or run against any database other than PostgreSQL 16.

## LLM provider

**Claude only.** `llm.LLMAdapter` is provider-agnostic by interface
(`ProviderClient`), but `llm.providers.claude.ClaudeProvider` is the only
concrete implementation that exists. There is no OpenAI, Gemini, Ollama,
or other provider integration.

## API surface

**No REST API for the pipeline.** The FastAPI application (`api`,
`main.py`) exposes only liveness/readiness health checks. `QueryMindEngine
.ask()` is a Python library entry point, not an HTTP endpoint — there is
no `/query` route or equivalent. `core.config.Settings` has no LLM/API-key
configuration field, confirming the pipeline has never been wired to the
web layer.

**No CLI.** There is no interactive command-line tool for asking
questions — only the seed-generation script (`scripts/seed_database.py`),
which is unrelated to the text-to-SQL pipeline.

## Streaming

**No token-level streaming.** `LLMAdapter.generate` and every phase after
it still work with a complete response, not a token stream — `Claude
Provider` makes one ordinary (non-streaming) Messages API call, and
`QueryMindEngine.ask()` still returns one complete `QueryMindResponse`
only once the entire pipeline finishes. What Phase 17 (`querymind
.streaming`) adds instead is *progress* streaming: `POST /query/stream`
(SSE) and `/ws/query` (WebSocket) report each pipeline stage
starting/completing/failing as it happens, ending with the same
complete `QueryMindResponse`/`BusinessAnswer` a non-streamed `POST
/query` call would return — never a partial or incremental *result*.

## Authentication and authorization

**None.** There is no user model, no auth middleware, no API key
validation, and no concept of a "caller" anywhere in the codebase beyond
the LLM provider's own API key (`LLMProviderConfig.api_key`).

## Visualization

**No visualization of any kind.** `result_formatter` explicitly does not
produce HTML, markdown tables, CSV, Excel, or chart output —
`BusinessAnswer.formatted_table` is structured data (columns and
deterministically-rendered value strings), not a rendered artifact.

## Caching

**No semantic cache, and no cache of any kind is actually active.** Every
phase from `prompt_compiler` onward defines a `<Phase>Cache` `Protocol`
and ships a `NoOp<Phase>Cache` that satisfies it without storing anything;
none of the real engines (`SQLGenerationEngine`, `SQLValidationEngine`,
`SQLRepairEngine`, `SQLExecutionEngine`, `ResultFormatterEngine`,
`QueryMindEngine`) currently accept or call a cache instance. There is no
semantic similarity cache for previously-asked questions.

## Execution history

**No execution history or audit log.** Each `QueryMindEngine.ask()` call
is entirely independent; nothing persists a record of past questions,
generated SQL, or results anywhere. `PipelineStatistics` is returned to
the caller for that one call only and is not stored.

## Multi-turn conversations

**No conversation state.** Every question is parsed and answered in
complete isolation — `QueryContext`/`LinkedQueryContext`/etc. carry no
reference to any prior question, and there is no mechanism for a follow-up
question ("what about last month?") to be interpreted relative to a
previous one.

## Distributed execution

**Single-process only.** `QueryMindEngine`/`PipelineRunner` run entirely
within one Python process using one `AsyncEngine` connection pool. There
is no distributed task queue, no worker pool, and no mechanism for
running multiple pipeline stages across separate processes or machines.

## Observability

**Per-call timing only, not exported anywhere.** `PipelineStatistics`
gives detailed per-stage latency for one call, returned to the caller —
but there is no metrics exporter (Prometheus, OpenTelemetry, or
otherwise), no distributed tracing, and no aggregation across calls.
Logging (`structlog`) exists at the application-foundation layer (Phase
1) but the pipeline packages themselves do not log through it.

## Result caching / idempotency

**Every call re-runs the entire pipeline.** Asking the same question
twice re-parses it, re-links the schema, re-retrieves examples, and
re-calls the LLM — there is no deduplication or memoization of any kind
(consistent with [Caching](#caching) above).

## Deployment

**Local/single-host only, beyond the existing container images.** A
`Dockerfile` and `docker-compose.yml` exist for running the app and
database together on one host; there are no Kubernetes manifests, no
CI/CD pipeline definitions, and no infrastructure-as-code for any cloud
provider.
