# Text-to-SQL Analytics Engine

Production-grade foundation for a Text-to-SQL analytics platform. **This
repository currently implements Phase 1 only: the application skeleton,
infrastructure, and tooling.** No AI pipeline, SQL generation, or business
domain models exist yet — those are later phases, built on top of this
foundation.

## What Phase 1 delivers

A running FastAPI service with:

- Async PostgreSQL connectivity (SQLAlchemy 2.0 + asyncpg)
- Environment-driven configuration (Pydantic Settings) — no hardcoded values
- Structured (JSON/console) logging with per-request correlation IDs
- Liveness/readiness health endpoints
- Alembic wired up for async migrations
- Docker + Docker Compose for a one-command local stack
- Ruff, MyPy (strict), and pytest configured and passing
- A layered structure future phases (domain, application, infrastructure)
  will build inside without restructuring what's already here

## Architecture

```
src/querymind/
├── main.py              # Composition root: builds the FastAPI app (app factory)
├── core/
│   ├── config.py         # Settings (env-driven, no hardcoded values)
│   └── logging.py        # structlog configuration
├── api/                  # Presentation layer
│   ├── deps.py            # Shared FastAPI dependencies (settings, DB session)
│   ├── middleware.py       # Request-ID / logging-context middleware
│   └── v1/
│       ├── router.py        # Aggregates all v1 endpoint routers
│       └── endpoints/
│           └── health.py     # Liveness + readiness probes
└── db/                    # Infrastructure layer (persistence)
    ├── base.py             # Shared SQLAlchemy DeclarativeBase + naming convention
    ├── engine.py            # Async engine factory
    └── session.py            # Session factory + transaction-scoped session helper
```

`domain/` and `application/` packages are deliberately **not** created yet.
An empty package is placeholder code, and this phase has no business
concepts to put in them — Phase 2 introduces the first bounded context and
adds those layers around real models, not speculative ones.

### Key architectural decisions

**Layered structure (`api` / `core` / `db`), not a single flat package.**
`api` (presentation) depends on `db` (infrastructure) only through typed
FastAPI dependencies in `api/deps.py`; `db` has zero FastAPI imports. This
means the persistence layer stays usable from a script or worker in a
later phase without dragging in the web framework, and it's the seam
future `domain`/`application` layers will sit behind.

**App factory (`create_app()`) instead of a module-level `app = FastAPI()`
only.** A factory can be called with an explicit `Settings` instance, which
is what makes the test suite hermetic (see `tests/conftest.py`) — tests
never depend on a real `.env` file or a real database being reachable for
tests that don't need one.

**Settings built from discrete Postgres fields, not one `DATABASE_URL`.**
`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` are the exact
variable names the official `postgres` Docker image reads to initialize
itself. Sourcing the app's connection string from those same variables
(via a computed field in `core/config.py`) guarantees the app and the
database container can never drift out of sync with different credentials.

**Liveness vs. readiness as separate endpoints.** `/health/live` has no
dependencies and answers "is this process alive" (used to decide whether
to *restart* a container). `/health/ready` executes `SELECT 1` against the
database and answers "can this process serve traffic" (used to decide
whether to *route* to it). Merging them would cause a transient database
blip to kill and restart otherwise-healthy application instances.

**Session-per-request via `app.state`, not a global engine.** The engine
and session factory are created once in the FastAPI `lifespan` handler and
attached to `app.state`, then handed out per-request through
`get_db_session` in `api/deps.py`. This avoids both a bare module-level
global (hard to override in tests) and re-creating the connection pool
per-request (expensive and eventually exhausts the database's connection
limit).

**Structured logging via `structlog`, integrated with stdlib `logging`.**
Uvicorn and any third-party library that uses stdlib `logging` are routed
through the same processor pipeline as application logs, so every log line
— ours or not — comes out in the same shape (JSON in production, colorized
console in development). `RequestContextMiddleware` binds a request ID via
`structlog.contextvars` so every log line for a request carries it
automatically, without threading a request ID through every function call.

**Explicit naming convention on `Base.metadata`.** Postgres auto-generates
opaque constraint/index names (e.g. `users_email_key1`) that differ across
environments unless named explicitly. The naming convention in `db/base.py`
makes Alembic's autogenerate produce stable, reproducible migration diffs.

**Multi-stage Dockerfile.** The `builder` stage has `uv` and build
artifacts; only the resulting virtualenv is copied into the slim `runtime`
stage, which runs as a non-root user. This keeps the production image
small and reduces its attack surface.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker + Docker Compose (for the containerized workflow)
- A running PostgreSQL 16 instance (provided by Docker Compose, or your own)

## Setup

### 1. Configure environment variables

```bash
cp .env.example .env
# then edit .env — at minimum, set a real POSTGRES_PASSWORD
```

Every configurable value is documented in `.env.example` and loaded through
`src/querymind/core/config.py::Settings`. Nothing in the application reads
`os.environ` directly outside that one module.

### 2a. Run everything with Docker Compose (recommended)

```bash
docker compose up --build
```

This starts Postgres and the API together. The API waits for Postgres to
report healthy (`pg_isready`) before starting, and exposes:

- `http://localhost:8000/api/v1/health/live`
- `http://localhost:8000/api/v1/health/ready`
- `http://localhost:8000/docs` (interactive OpenAPI docs)

### 2b. Run locally without Docker

```bash
uv sync                    # install dependencies into .venv
# ensure Postgres is reachable at the host/port in your .env (POSTGRES_HOST=localhost)
uv run alembic upgrade head
uv run uvicorn querymind.main:app --reload
```

A `Makefile` wraps the common commands:

| Command | Description |
|---|---|
| `make install` | Install dependencies with uv |
| `make run` | Run the API locally with autoreload |
| `make lint` | Lint with Ruff |
| `make format` | Format with Ruff |
| `make typecheck` | Static type-check with MyPy (strict) |
| `make test` | Run the test suite with coverage |
| `make check` | Lint + typecheck + test — the full local gate |
| `make migrate` | Apply Alembic migrations |
| `make migrate-autogenerate name="..."` | Autogenerate a migration from model changes |
| `make docker-up` | Start the full stack via Docker Compose |
| `make docker-down` | Stop the stack |

(No `make` on Windows outside WSL/Git Bash? Run the underlying command from
the `Makefile` directly, e.g. `uv run pytest`.)

## Database migrations

Alembic (`alembic/env.py`) runs asynchronously against the same `Settings`
and `Base.metadata` the application itself uses — there is exactly one
definition of the schema and one place the database URL comes from. As
future phases add ORM models, import them at the top of `alembic/env.py`
so autogenerate can see them:

```python
from querymind.domain.some_module import models as _  # noqa: F401
```

## Testing

```bash
uv run pytest
```

`tests/conftest.py` builds the app with an explicit, hermetic `Settings`
instance (no real `.env` or database required for tests that don't touch
one) and drives it in-process via `httpx.AsyncClient` + `asgi-lifespan`, so
the app's real startup/shutdown lifecycle runs exactly as it would in
production.

## Verification checklist

- [ ] `cp .env.example .env` and set a real `POSTGRES_PASSWORD`
- [ ] `docker compose up --build` starts both services without error
- [ ] `curl http://localhost:8000/api/v1/health/live` → `{"status":"ok"}`
- [ ] `curl http://localhost:8000/api/v1/health/ready` → `{"status":"ok","database":"ok"}`
- [ ] `uv run ruff check .` passes
- [ ] `uv run mypy src` passes
- [ ] `uv run pytest` passes