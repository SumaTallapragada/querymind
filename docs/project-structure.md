# Project Structure

Every top-level package under `src/querymind/`, in dependency order, with
its responsibility and internal layout. See
[`ARCHITECTURE.md`](../ARCHITECTURE.md) for how they relate to each other,
and [`CONTRIBUTING.md`](../CONTRIBUTING.md#folder-organization) for the
common shape every pipeline phase package follows.

## Foundation

### `core/`

Environment-driven configuration and logging — read by every other layer.

- `config.py` — `Settings` (Pydantic Settings, sourced from `.env`/the
  process environment) and `get_settings()` (an `lru_cache`-memoized
  process-wide instance). The one place `os.environ` is read.
- `logging.py` — `structlog` configuration; JSON output in production,
  colorized console output in development.

### `db/`

Async SQLAlchemy infrastructure — no business logic, no FastAPI imports.

- `base.py` — the shared `Base` declarative class and its explicit
  constraint/index naming convention (so Alembic autogenerate produces
  stable, reproducible diffs).
- `engine.py` — `create_engine(settings)`, the one place the application's
  `AsyncEngine` is constructed. Every later phase that touches the
  database (`sql_execution`, and anything using `MetadataRegistry`) is
  built on top of an engine created here — none of them construct a
  second one.
- `session.py` — session factory and a transaction-scoped session helper
  for request-handler and script use.

### `models/`

SQLAlchemy ORM models for the 14-table domain schema: `customer.py`
(`customers`, `customer_addresses`), `order.py` (`orders`, `order_items`),
`payment.py`, `product.py` (`products`, `product_categories`),
`supplier.py`, `inventory.py` (`inventory`, `warehouses`), `shipment.py`,
`promotion.py`, `review.py` (`product_reviews`), `returns.py`. Every model
inherits from `db.base.Base`; `models/__init__.py` imports every module so
`import querymind.models` alone registers the complete schema on
`Base.metadata` — this is what Alembic autogenerate and
`querymind.metadata.MetadataExtractor` both rely on.

### `seeds/`

Synthetic dataset generation and persistence. One generator class per
domain table (`customers.py`, `orders.py`, `payments.py`, ...), each
consuming a shared `SeedContext`/`Random` for reproducibility; `rules/`
holds the business-consistency rules each generator enforces (e.g. an
order's payment amount must reconcile with its line items).
`generator.py`'s `SeedOrchestrator` runs every generator in a fixed
dependency order and persists each stage before the next begins;
`persistence.py`'s `AsyncSessionTransactionRunner` is the concrete,
single-shared-session persistence strategy; `report.py` builds a
post-generation summary and runs `DatasetValidator` against what actually
landed in PostgreSQL. `scripts/seed_database.py` is the CLI entry point —
see [`getting-started.md`](getting-started.md#4-seed-the-database).

### `metadata/`

The single source of truth for "what does the database look like,
structurally and in business terms" — infrastructure, not an AI component:
no LLM calls, no prompt engineering, no schema-linking logic. Every
pipeline phase that needs schema information asks `MetadataRegistry`
(`registry.py`), never `querymind.models` or a live database connection,
directly. `extractor.py` reads structure from `Base.registry`;
`dictionary.py` layers a business-friendly `ColumnDictionary` (display
names, search keywords) on top; `relationships.py` builds the
`RelationshipGraph` used for join-path resolution; `models.py` defines the
resulting metadata types (`TableMetadata`, `ColumnMetadata`,
`RelationshipMetadata`, ...); `cache.py`/`serializer.py`/`exceptions.py`
follow the same shape as every later phase.

## Presentation

### `api/` and `main.py`

FastAPI presentation layer. `main.py`'s `create_app()` factory builds the
app (settings, logging, middleware, routers, a lifespan handler that owns
the database engine's lifecycle) — there is no module-level
`app = FastAPI()` outside the factory itself. `api/deps.py` exposes typed
FastAPI dependencies (settings, a per-request DB session);
`api/middleware.py` binds a request ID to every log line via
`structlog.contextvars`; `api/v1/endpoints/health.py` implements
liveness (`/health/live`) and readiness (`/health/ready`, which runs
`SELECT 1`) probes. **This layer does not yet call into the QueryMind
pipeline** — see the [roadmap](../README.md#project-roadmap).

## The text-to-SQL pipeline

Each package below is documented in full, phase by phase, in
[`pipeline.md`](pipeline.md). This is the structural summary.

| Package | Phase | Key files |
|---|---|---|
| `nlu/` | 5 | `parser.py` (entry point), `normalizer.py`, `intents.py`, `entities.py`, `metrics.py`, `filters.py`, `time.py`, `sorting.py`, `limits.py`, `models.py` |
| `schema_linker/` | 6 | `linker.py` (entry point), `resolver.py`, `candidates.py`, `matcher.py`, `scorer.py`, `ambiguity.py`, `relationships.py`, `models.py`, `cache.py` |
| `business_knowledge/` | 7 | `registry.py` (entry point), `catalog.py`, `loader.py`, `resolver.py`, `models.py`, `serializer.py` |
| `query_library/` | 8 | `registry.py` (entry point), `catalog.py`, `loader.py`, `search.py`, `validator.py`, `models.py` |
| `retrieval/` | 9 | `engine.py` (entry point), `signals.py`, `scorer.py`, `ranker.py`, `matcher.py`, `explanations.py`, `statistics.py`, `models.py` |
| `prompt_compiler/` | 10A | `compiler.py` (entry point), `sections.py`, `templates.py`, `budget.py`, `validator.py`, `formatter.py`, `models.py` |
| `llm/` | 10B | `adapter.py` (entry point), `providers/claude.py`, `providers/base.py`, `client.py`, `parser.py`, `retry.py`, `config.py`, `metrics.py`, `models.py` |
| `sql_generation/` | 11A | `engine.py` (entry point), `extractor.py`, `normalizer.py`, `parser.py` (statement-type detection), `statistics.py`, `models.py` |
| `sql_validation/` | 11B | `engine.py` (entry point), `parser.py` (sqlglot wrapper), `registry.py`, `validators/` (10 files, one per validator), `models.py` |
| `sql_repair/` | 12 | `engine.py` (entry point), `planner.py`, `prompt_builder.py`, `strategy.py`, `validator.py`, `parser.py`, `llm_adapter.py`, `models.py` |
| `sql_execution/` | 13 | `engine.py` (entry point), `connection.py`, `executor.py`, `formatter.py`, `validator.py` (`ExecutionGuard`), `models.py` |
| `result_formatter/` | 14 | `engine.py` (entry point), `formatter.py`, `value_formatter.py`, `summarizer.py`, `answer_generator.py`, `statistics.py`, `models.py` |
| `orchestrator/` | 15 | `engine.py` (`QueryMindEngine`, entry point), `pipeline.py` (`PipelineRunner`), `statistics.py`, `models.py` |

Every phase package additionally has its own `exceptions.py` (a
`<Phase>Error` hierarchy), `cache.py` (a `<Phase>Cache` `Protocol` plus a
`NoOp<Phase>Cache`), and `serializer.py` (`to_dict`/`to_json`/`to_yaml`) —
omitted from the table above since they follow one identical, documented
shape across every phase (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md#folder-organization)).

## Tests

`tests/` mirrors `src/querymind/` exactly — one directory per package,
same name, same relative file layout (`test_<module>.py` per
`<module>.py`, plus `conftest.py`, `test_engine.py`, and
`test_integration.py`). `tests/api/` covers the FastAPI health endpoints;
`tests/conftest.py` is the one repo-wide fixture file (a hermetic
`Settings` instance and an in-process `httpx.AsyncClient` for API tests).
See [`testing.md`](testing.md) for the full test philosophy.

## Everything else at the repository root

- `scripts/seed_database.py` — CLI entry point for seed generation (see
  [`getting-started.md`](getting-started.md#4-seed-the-database)).
- `alembic/` — async database migrations (`env.py`, `versions/`).
- `docs/` — this directory.
- `Dockerfile`, `docker-compose.yml` — multi-stage container build and the
  local app+database stack.
- `Makefile` — thin wrappers around the `uv run`/`docker compose` commands
  used throughout this documentation.
- `pyproject.toml` — dependencies, and all Ruff/MyPy/pytest/coverage
  configuration.
