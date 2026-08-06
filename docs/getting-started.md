# Getting Started

This walks through getting QueryMind running locally from a clean clone,
end to end: environment, dependencies, database, seed data, and the test
suite. For the one-paragraph version, see the [README](../README.md); this
document goes into more detail on each step and what to check if it
doesn't work.

## 1. Environment setup

**Requirements:**

- Python 3.12 (the project pins `requires-python = ">=3.12,<3.13"`)
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker + Docker Compose (recommended for the database), or a local
  PostgreSQL 16 instance
- Git

Clone the repository and create your local environment file:

```bash
git clone <repository-url>
cd Text-to-SQLAnalyticsEngine
cp .env.example .env
```

Open `.env` and, at minimum, set a real `POSTGRES_PASSWORD` (the example
value is a placeholder and will not work against a real database). Every
other value in `.env.example` has a working default for local development.
`.env` is git-ignored — never commit real credentials.

Every setting the application reads comes from this one file, loaded
through `querymind.core.config.Settings`. Nothing else in the codebase
reads `os.environ` directly.

## 2. Install dependencies

```bash
uv sync
```

This creates `.venv` and installs both runtime and development
dependencies (Ruff, MyPy, pytest, and friends — see `[dependency-groups]`
in `pyproject.toml`) in one step. From here on, run project commands
through `uv run <command>` so they execute inside that environment.

## 3. Create the database

**Option A — Docker Compose (recommended):**

```bash
docker compose up --build
```

This starts a `postgres:16-alpine` container using the `POSTGRES_USER`/
`POSTGRES_PASSWORD`/`POSTGRES_DB` values from `.env` (the same file the
application reads, so the two can never drift out of sync) and the
FastAPI app together. The app container waits for Postgres to report
healthy before starting.

If you already have something listening on port 5432 locally, set
`POSTGRES_PORT` in `.env` to a free host port (e.g. `5433`) — Compose maps
that to the container's internal 5432 regardless.

**Option B — a local or externally managed PostgreSQL 16 instance:**

Make sure `POSTGRES_HOST`/`POSTGRES_PORT`/`POSTGRES_USER`/
`POSTGRES_PASSWORD`/`POSTGRES_DB` in `.env` point at it, then apply the
schema:

```bash
uv run alembic upgrade head
```

This runs every migration under `alembic/versions/` against
`Settings.database_url`, creating the 14 domain tables (customers, orders,
payments, products, suppliers, inventory, warehouses, shipments,
promotions, reviews, returns, and their supporting tables) plus their
indexes and constraints.

## 4. Seed the database

The schema starts empty. `querymind.seeds` generates a coherent, Faker-driven
synthetic e-commerce dataset and persists it in dependency order (customers
before orders, orders before payments, and so on) through
`scripts/seed_database.py`:

```bash
uv run python scripts/seed_database.py --dataset-size small
```

Start with `--dataset-size small` (a few hundred rows per table) — it's
fast and enough to exercise every part of the pipeline. Once it's working,
generate more realistic volumes:

```bash
uv run python scripts/seed_database.py --dataset-size medium
uv run python scripts/seed_database.py                    # full-scale default
uv run python scripts/seed_database.py --scenario black_friday
```

The script prints a generation summary, then runs a post-generation
`DatasetValidator` pass against the real database and prints a validation
summary. A non-zero exit code means the validator found something
inconsistent — re-run with a fresh database (`docker compose down -v &&
docker compose up -d db`, or truncate the tables) rather than re-seeding on
top of existing data.

`make seed`, `make seed-small`, and `make seed-medium` wrap the same
commands.

## 5. Run QueryMind

The pipeline is not yet exposed over HTTP (see the
[roadmap](../README.md#project-roadmap)) — the API server currently only
exposes health checks. To ask QueryMind a real question today, use it as a
Python library, wiring one instance of each phase's own public entry point
into a `PipelineRunner`/`QueryMindEngine`. See
[Example usage in the README](../README.md#example-usage) for a complete,
runnable script, and [`docs/pipeline.md`](pipeline.md) for a worked example
with real captured output.

The FastAPI app itself (health checks only, today) can still be started
the normal way:

```bash
uv run uvicorn querymind.main:app --reload
```

- `http://localhost:8000/api/v1/health/live`
- `http://localhost:8000/api/v1/health/ready` (checks the database with
  `SELECT 1`)
- `http://localhost:8000/docs` — interactive OpenAPI docs

## 6. Run tests

```bash
uv run pytest
```

The suite needs a reachable PostgreSQL instance — most phases from
`sql_execution` onward run real queries against it (they do not require
seeded data specifically, but a running, migrated database). Every test
that would otherwise need the LLM replaces the network with
`httpx.MockTransport`, so no test ever makes a real API call and no
`ANTHROPIC_API_KEY` (or similar) is required to run the suite.

```bash
uv run pytest tests/orchestrator -q   # a single phase's suite
uv run pytest -q                      # everything
```

Then the rest of the local quality gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Or all of lint + typecheck + test in one command: `make check`.

## Troubleshooting

- **`pydantic_core.ValidationError` on startup mentioning `postgres_password`
  or similar** — `.env` is missing or a required field wasn't set; re-check
  step 1.
- **Tests fail with a connection error** — the database isn't reachable at
  `POSTGRES_HOST`/`POSTGRES_PORT` from wherever you're running `pytest`;
  confirm `docker compose up` (or your local Postgres) is actually running
  and that `.env`'s host/port match it.
- **Seeding fails with a unique-constraint violation** — you're re-seeding
  into a database that already has data from a previous run. Reset the
  database (`docker compose down -v && docker compose up -d db`, then
  `uv run alembic upgrade head`) before seeding again.
- **`make` isn't found (plain Windows outside WSL/Git Bash)** — run the
  underlying command from the `Makefile` directly, e.g.
  `uv run pytest` instead of `make test`.
