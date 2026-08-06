# QueryMind — Text-to-SQL Analytics Engine

**Version:** 1.0.0 (QueryMind Core Engine) — see
[`CHANGELOG.md`](CHANGELOG.md) and [`VERSION_HISTORY.md`](VERSION_HISTORY.md).

QueryMind turns a natural language business question into a real, executed
SQL query and a formatted answer — without an ORM query, a hardcoded
report, or a human writing SQL by hand. It is built as a sequence of small,
independently testable engines, each owning exactly one responsibility,
composed by a single orchestrator into one end-to-end pipeline.

**Status:** the core engine (natural language question → `BusinessAnswer`)
is feature-complete through Phase 15 and fully covered by tests running
against a real PostgreSQL database. It is not yet exposed over HTTP — see
[Project roadmap](#project-roadmap) and
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) for the complete
list of what this release does not include.

## Goals

- Convert an analyst's natural language question into correct, validated,
  read-only SQL against a real relational schema.
- Never guess silently: every stage that can fail — ambiguous schema
  linking, invalid SQL, a failed execution — produces a structured,
  inspectable result instead of a best-effort guess.
- Keep every phase substitutable and independently testable through
  constructor dependency injection, with no global state and no singleton
  services anywhere in the pipeline.
- Reuse deterministic techniques (rule-based parsing, `sqlglot` ASTs, schema
  metadata, a curated example library) wherever they are sufficient, and
  reserve the LLM call for exactly the one step that needs it — turning a
  compiled prompt into SQL text.

## Key features

- **Deterministic NLU** — intent, entities, metrics, filters, time ranges,
  sorting, and limits extracted from a question with no embeddings, no
  vector search, and no LLM call.
- **Schema linking against a live metadata registry** — business concept
  names resolved to real tables/columns via exact match, business
  dictionary lookup, synonyms, alias expansion, and fuzzy matching, with
  every unresolved concept recorded as an explicit ambiguity rather than a
  silent guess.
- **Explainable hybrid retrieval** — the most relevant few-shot examples
  from a curated query library, ranked by eight independent, weighted
  signals with a full score breakdown per candidate.
- **Token-budgeted prompt compilation** — seven independently built prompt
  sections, validated and trimmed to fit a configurable token budget.
- **Provider-agnostic LLM adapter** — retries, timeouts, and response
  parsing isolated behind one interface; the only component in the whole
  pipeline that makes a network call.
- **AST-based SQL validation** — ten independent, read-only validators
  (syntax, schema, table, column, join, function, aggregate, alias,
  business rule, dialect) built on `sqlglot`, never regex.
- **Bounded, automatic SQL repair** — invalid SQL is fed back to the LLM
  with the exact validation errors, over a capped retry loop, with the
  full attempt history preserved.
- **Defense-in-depth read-only execution** — an independent AST guard plus
  a database-level read-only transaction, so a write can never reach the
  database even if a validation gap exists upstream.
- **Deterministic result formatting** — query rows converted into an
  immutable, locale-independent `BusinessAnswer` with no charts, no
  markdown, and no invented business interpretation.
- **One orchestrator, fully wired** — `QueryMindEngine.ask()` runs the
  complete pipeline end to end, times every stage independently, and never
  raises — every failure becomes a structured, typed response.

## Architecture

```mermaid
flowchart TB
    Q["Natural language question"] --> NLU["NLU Engine\n(querymind.nlu)"]
    NLU --> SL["Schema Linker\n(querymind.schema_linker)"]
    SL --> BK["Business Knowledge\n(querymind.business_knowledge)"]
    BK --> RET["Hybrid Retrieval\n(querymind.retrieval)"]
    RET --> PC["Prompt Compiler\n(querymind.prompt_compiler)"]
    PC --> LLM["LLM Adapter\n(querymind.llm)"]
    LLM --> GEN["SQL Generation\n(querymind.sql_generation)"]
    GEN --> VAL["SQL Validation\n(querymind.sql_validation)"]
    VAL -->|invalid| REP["SQL Repair\n(querymind.sql_repair)"]
    VAL -->|valid| EXEC["SQL Execution\n(querymind.sql_execution)"]
    REP --> EXEC
    EXEC --> FMT["Result Formatter\n(querymind.result_formatter)"]
    FMT --> ANS["BusinessAnswer"]

    ORCH["Orchestrator\n(querymind.orchestrator)"] -.wires and sequences.-> NLU
    ORCH -.-> SL
    ORCH -.-> RET
    ORCH -.-> PC
    ORCH -.-> GEN
    ORCH -.-> VAL
    ORCH -.-> REP
    ORCH -.-> EXEC
    ORCH -.-> FMT
```

Metadata about the real database schema (`querymind.metadata`) is consumed
directly by schema linking, validation, and repair — never inferred, never
duplicated. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full layered
picture, dependency direction, and every package's responsibility.

## End-to-end pipeline

| # | Stage | Package | Input → Output |
|---|---|---|---|
| 1 | NLU | `querymind.nlu` | question `str` → `QueryContext` |
| 2 | Schema Linking | `querymind.schema_linker` | `QueryContext` → `LinkedQueryContext` |
| 3 | Business Knowledge | `querymind.business_knowledge` | (loaded, consumed by retrieval/validation) |
| 4 | Retrieval | `querymind.retrieval` | `LinkedQueryContext` → `RetrievedKnowledgeBundle` |
| 5 | Prompt Compilation | `querymind.prompt_compiler` | `RetrievedKnowledgeBundle` → `CompiledPrompt` |
| 6 | LLM | `querymind.llm` | `CompiledPrompt` → `LLMResponse` (called inside step 7) |
| 7 | SQL Generation | `querymind.sql_generation` | `CompiledPrompt` → `GeneratedSQL` |
| 8 | SQL Validation | `querymind.sql_validation` | `GeneratedSQL` → `SQLValidationResult` |
| 9 | SQL Repair (conditional) | `querymind.sql_repair` | invalid `GeneratedSQL` → `SQLRepairResult` |
| 10 | SQL Execution | `querymind.sql_execution` | valid SQL → `SQLExecutionResult` |
| 11 | Result Formatting | `querymind.result_formatter` | successful `SQLExecutionResult` → `BusinessAnswer` |

`querymind.orchestrator.QueryMindEngine.ask(question)` runs all eleven
stages and returns one immutable `QueryMindResponse` — see
[`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) for what flows between every stage
and why each phase exists.

## Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI (health endpoints only today — see [roadmap](#project-roadmap)) |
| Database | PostgreSQL 16, async via SQLAlchemy 2.0 + asyncpg |
| Migrations | Alembic (async) |
| Data models | Pydantic v2 — every cross-phase model is `frozen=True`, `extra="forbid"` |
| SQL parsing | `sqlglot` — every AST-level check (validation, repair, execution guard) |
| LLM provider | Anthropic Claude, via a raw `httpx` client (no vendor SDK dependency) |
| Config | `pydantic-settings`, environment-driven, no hardcoded values |
| Logging | `structlog`, JSON in production / console in development |
| Dependency management | [`uv`](https://docs.astral.sh/uv/) |
| Linting / formatting | Ruff |
| Static typing | MyPy, `strict = true` |
| Testing | pytest, `pytest-asyncio`, `pytest-cov`, `httpx.MockTransport` for the LLM |
| Synthetic data | Faker-driven seed generators for a full e-commerce dataset |

## Installation

```bash
git clone <repository-url>
cd Text-to-SQLAnalyticsEngine
cp .env.example .env
# edit .env — at minimum, set a real POSTGRES_PASSWORD
uv sync
```

`uv sync` installs both runtime and development dependencies into `.venv`.
Every configurable value is documented in `.env.example` and loaded through
`querymind.core.config.Settings` — nothing in the application reads
`os.environ` directly anywhere else.

## Database setup

**Option A — Docker Compose (recommended):**

```bash
docker compose up --build
```

Starts PostgreSQL 16 and the FastAPI app together; the app waits for
Postgres to report healthy before starting.

**Option B — local Postgres, run the app on the host:**

```bash
# ensure Postgres is reachable at POSTGRES_HOST/POSTGRES_PORT in .env
uv run alembic upgrade head
uv run uvicorn querymind.main:app --reload
```

Apply the schema (14 tables — customers, orders, payments, products,
suppliers, inventory, warehouses, shipments, promotions, reviews, returns,
and their supporting tables):

```bash
uv run alembic upgrade head
```

## Seed generation

The `querymind.seeds` package generates a coherent, referentially valid
synthetic e-commerce dataset (customers, orders, payments, shipments,
inventory, promotions, reviews, returns, ...) and persists it through one
shared database session, in dependency order, via
`scripts/seed_database.py`:

```bash
uv run python scripts/seed_database.py                          # full-scale default dataset
uv run python scripts/seed_database.py --dataset-size small     # quick smoke test
uv run python scripts/seed_database.py --dataset-size medium
uv run python scripts/seed_database.py --scenario black_friday  # a named demand scenario
uv run python scripts/seed_database.py --seed 7                 # reproducible run
```

Equivalent `make` targets: `make seed`, `make seed-small`,
`make seed-medium`. After generation, the script runs a post-generation
`DatasetValidator` pass against PostgreSQL and prints a summary.

## Running tests

```bash
uv run pytest
```

The suite requires a reachable PostgreSQL instance (see
[Database setup](#database-setup)) — most phases from `sql_execution`
onward run real queries against it; every LLM-touching test replaces the
network with `httpx.MockTransport`, so no test ever makes a real API call.
`tests/conftest.py` also builds the FastAPI app with an explicit, hermetic
`Settings` instance for the API-layer tests, independent of `.env`.

```bash
uv run pytest tests/orchestrator -q   # one phase's suite in isolation
uv run pytest -q                      # the whole repository
```

See [`docs/testing.md`](docs/testing.md) for the full test philosophy.

## Running quality checks

```bash
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
uv run mypy src                # static typing (strict)
uv run pytest                   # tests + coverage
```

Or the combined local gate:

```bash
make check   # lint + typecheck + test
```

## Example usage

The engine is not yet exposed over HTTP (see
[roadmap](#project-roadmap)) — today it is used as a Python library. The
composition root wires one already-constructed instance of every phase's
own public entry point into a `PipelineRunner`, then a `QueryMindEngine`:

```python
import asyncio

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.llm.adapter import LLMAdapter
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import LLMProvider
from querymind.llm.providers.claude import ClaudeProvider
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.models.base import Base
import querymind.models  # noqa: F401 -- registers every ORM model on Base.metadata
from querymind.nlu import QueryParser
from querymind.orchestrator import PipelineRunner, QueryMindEngine
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library import QueryLibraryRegistry
from querymind.result_formatter import ResultFormatterEngine
from querymind.retrieval import RetrievalEngine
from querymind.schema_linker import SchemaLinker
from querymind.sql_execution import DatabaseConnectionProvider, SQLExecutionEngine
from querymind.sql_generation import SQLGenerationEngine
from querymind.sql_repair import SQLRepairEngine, SQLRepairLLMAdapter
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation import SQLValidationEngine


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)

    metadata_registry = MetadataRegistry(MetadataExtractor(Base.registry), ColumnDictionary.default())
    metadata_registry.load()
    business_knowledge = BusinessKnowledgeRegistry()
    business_knowledge.load()
    query_library = QueryLibraryRegistry()
    query_library.load()

    llm_config = LLMProviderConfig(provider=LLMProvider.CLAUDE, model="claude-sonnet-5", api_key=...)
    llm_adapter = LLMAdapter(ClaudeProvider(llm_config), llm_config)
    validation_engine = SQLValidationEngine(metadata_registry, business_knowledge)

    runner = PipelineRunner(
        nlu_parser=QueryParser(),
        schema_linker=SchemaLinker(metadata_registry),
        business_knowledge_registry=business_knowledge,
        retrieval_engine=RetrievalEngine(query_library=query_library, business_knowledge=business_knowledge),
        prompt_compiler=PromptCompiler(),
        sql_generation_engine=SQLGenerationEngine(llm_adapter),
        sql_validation_engine=validation_engine,
        sql_repair_engine=SQLRepairEngine(SQLRepairLLMAdapter(llm_adapter), RepairValidator(validation_engine)),
        sql_execution_engine=SQLExecutionEngine(DatabaseConnectionProvider(engine)),
        result_formatter_engine=ResultFormatterEngine(),
    )

    response = await QueryMindEngine(runner).ask("Who are our top 5 customers by revenue?")
    print(response.status, response.business_answer)
    await engine.dispose()


asyncio.run(main())
```

`QueryMindEngine.ask()` never raises — `response.status` is always either
`SUCCESS` (`response.business_answer` populated) or `FAILED`
(`response.error` populated). See [`docs/pipeline.md`](docs/pipeline.md)
for a worked example with real output.

## Folder structure

```
src/querymind/
├── main.py                # FastAPI composition root (app factory)
├── core/                    # Settings, logging — read by every layer
├── api/                     # Presentation layer (health endpoints today)
├── db/                      # Async engine/session infrastructure
├── models/                  # SQLAlchemy ORM models (14 domain tables)
├── seeds/                   # Synthetic dataset generation + persistence
├── metadata/                 # Schema metadata registry (Phase 2-3)
├── nlu/                      # Phase 5   — Natural Language Understanding
├── schema_linker/              # Phase 6   — Semantic Schema Linker
├── business_knowledge/          # Phase 7   — Business Knowledge Engine
├── query_library/              # Phase 8   — Query Intelligence Library
├── retrieval/                  # Phase 9   — Knowledge Retrieval Engine
├── prompt_compiler/             # Phase 10A — Prompt Compiler
├── llm/                        # Phase 10B — LLM Adapter
├── sql_generation/              # Phase 11A — SQL Generation Engine
├── sql_validation/              # Phase 11B — SQL Validation Engine
├── sql_repair/                 # Phase 12  — SQL Repair Engine
├── sql_execution/               # Phase 13  — SQL Execution Engine
├── result_formatter/            # Phase 14  — Result Formatter / Answer Generator
└── orchestrator/                # Phase 15  — End-to-End QueryMind Orchestrator

tests/                        # One directory per package above, same names
scripts/seed_database.py       # CLI entry point for seed generation
alembic/                      # Async database migrations
docs/                         # Extended documentation (this file links out to it)
```

See [`docs/project-structure.md`](docs/project-structure.md) for every
package's responsibility in detail.

## Project roadmap

Implemented (Phases 1–15.5, released as v1.0.0): application foundation,
database schema and seeding, metadata engine, the complete eleven-stage
text-to-SQL pipeline described above ending at an immutable
`BusinessAnswer`, and a stabilization/release-readiness pass — see
[`VERSION_HISTORY.md`](VERSION_HISTORY.md) for the full narrative.

Not yet implemented — explicitly deferred, phase by phase, throughout this
project's history (see [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md)
for the complete, current list):

- REST API surface for the pipeline itself (`/query` or equivalent) —
  today `QueryMindEngine` is a library entry point, not an HTTP endpoint.
- CLI for interactive question-asking.
- Streaming responses.
- Observability/metrics export beyond the per-stage timings already
  collected in `PipelineStatistics`.
- Authentication/authorization.
- A frontend (React or otherwise).
- Result visualization — charts, HTML tables, CSV/Excel export.
- Result caching — every phase defines a cache `Protocol` and a
  `NoOp*` implementation, deliberately not wired up.
- Production deployment tooling beyond the existing `Dockerfile`/
  `docker-compose.yml` pair (Kubernetes manifests, CI/CD, etc.).

## License

Proprietary. No license has been formally selected yet — see
`pyproject.toml`'s `license` field. Replace this section before any public
release.
