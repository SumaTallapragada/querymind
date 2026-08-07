# Docker (Phases 19A–19B)

Containerization for the QueryMind backend and frontend. Phase 19A shipped two independently
buildable production images (`Dockerfile.backend`, `frontend/Dockerfile`). Phase 19B wires both
into `docker-compose.yml` as a complete three-service local production stack (`db` + `app` +
`frontend`) behind one reverse proxy, on one shared network, started and stopped with a single
command. It does not cover GitHub Actions/CI or Kubernetes — those are later phases.

## Images

| Image | Dockerfile | Base (runtime stage) | Runs as | Listens on |
| --- | --- | --- | --- | --- |
| Backend | `Dockerfile.backend` | `python:3.12-slim-bookworm` | non-root `app` | `$APP_PORT` (default `8000`) |
| Frontend | `frontend/Dockerfile` | `nginxinc/nginx-unprivileged:1.27-alpine` | non-root `nginx` | `8080` |

Both are multi-stage: a builder stage with the toolchain (`uv`/`npm`) and source, and a runtime
stage that only ever receives the already-built artifact (a `.venv` for the backend, `dist/`
for the frontend) — no compiler, package manager, or source tree ships in the final image.

### Relationship to the legacy root `Dockerfile`

The repository's original root `Dockerfile` (pre-Phase 19A) still exists, unmodified, but
`docker-compose.yml`'s `app` service now builds from `Dockerfile.backend` instead, as of Phase
19B — the two were never functionally reconciled by editing either one; Compose was simply
pointed at the newer image. The only difference between them is that `Dockerfile.backend` makes
the listen port configurable via `APP_PORT` (`EXPOSE`/`HEALTHCHECK`/`uvicorn --port` all read
it) instead of hardcoding `8000`, which is also why `docker-compose.yml`'s `app.ports` mapping
is `${APP_PORT:-8000}:${APP_PORT:-8000}` (both sides move together) rather than a hardcoded
container-side `8000`. The legacy `Dockerfile` is unused by Compose now and kept only for
anyone still building from it directly.

## Development

For day-to-day development, keep using what already works and is already verified:

```bash
uv sync && make run          # backend, with autoreload, against a reachable Postgres
cd frontend && npm run dev   # frontend, with HMR, proxying /api and /ws to localhost:8000
```

or `make docker-up`/`docker compose up -d` for the full stack (below). Neither of Phase 19A's
images is meant for hot-reload development — both are standalone production builds, and so is
the Compose stack they're wired into.

## Docker Compose: the full local production stack

`docker-compose.yml` runs all three services together, on one Compose-managed network
(`querymind`), with the frontend reverse-proxying REST/SSE/WebSocket traffic to the backend --
the same topology a real deployment would use, running locally.

```bash
docker compose up -d --build   # one-command startup: db -> app -> frontend, in health order
docker compose ps              # all three should show "healthy"
docker compose down            # one-command shutdown; add -v to also delete the Postgres volume
```

Once healthy, the whole application is reachable at `http://localhost:${FRONTEND_PORT:-8080}/`
-- the frontend serves the SPA and transparently proxies `/api/*`, the SSE endpoint, and
`/ws/*` to `app`, so nothing in the browser needs to know the backend exists on a different
port (or in a different container) at all.

### What's new vs. the Phase 19A images alone

- **`frontend` service**: builds `frontend/Dockerfile`, published on `${FRONTEND_PORT:-8080}`
  (host) -> `8080` (container), `depends_on: app: condition: service_healthy`.
- **`app` now builds from `Dockerfile.backend`**, not the legacy root `Dockerfile` (see above).
- **Explicit `querymind` network**: all three services attached to a named bridge network
  instead of relying on Compose's implicit default one -- functionally equivalent (Compose's
  default network is already a user-defined bridge with the same embedded DNS), but
  self-documenting for a stack meant to look like a real deployment.
- **`frontend/nginx.conf`'s REST/SSE/WebSocket `location` blocks are active**, proxying to
  `app:8000` through a Docker-DNS-resolved variable rather than a literal hostname (see the
  comment at the top of `nginx.conf` for why: a literal, unresolvable `proxy_pass` target
  would prevent nginx from starting at all, not just fail that one route).

### Verifying the stack

```bash
# REST
curl http://localhost:${FRONTEND_PORT:-8080}/api/v1/health

# Direct query (replace with a real question against your seeded data)
curl -X POST http://localhost:${FRONTEND_PORT:-8080}/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many rows are in the customers table?"}'

# SSE (Ctrl+C once you see event: frames)
curl -N -X POST http://localhost:${FRONTEND_PORT:-8080}/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "How many rows are in the customers table?"}'
```

A WebSocket client is needed for `/ws/query` (`curl` doesn't speak WebSocket) -- the frontend
itself exercises it directly from the browser (Dashboard page, streaming mode, WebSocket
transport).

**Persistent volume**: `postgres_data` is unchanged from Phase 19A/before -- `docker compose
down` (without `-v`) followed by `docker compose up -d` again brings the same data back, since
the named volume isn't removed. Only `docker compose down -v` deletes it.

## Production

### Build commands

```bash
# Backend (run from the repository root, so uv.lock/pyproject.toml/src are in the build context)
docker build -f Dockerfile.backend -t querymind-backend:latest .

# Frontend (run from frontend/, so package-lock.json/src are in the build context)
cd frontend
docker build -t querymind-frontend:latest .
```

### Run commands

```bash
# Backend — every value below is illustrative; set real ones. POSTGRES_PASSWORD and
# LLM_API_KEY are secrets and must never be baked into the image (see "Secrets" below).
docker run --rm -p 8000:8000 \
  -e POSTGRES_USER=querymind \
  -e POSTGRES_PASSWORD=change-me \
  -e POSTGRES_DB=querymind \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_PORT=5432 \
  -e LLM_API_KEY=sk-... \
  querymind-backend:latest

# Or, more conveniently, from an existing .env (see .env.example):
docker run --rm -p 8000:8000 --env-file .env querymind-backend:latest

# Frontend — static assets only; no backend connection required to serve the app shell
# (API calls will simply fail client-side until a backend/proxy is reachable — see nginx.conf).
docker run --rm -p 8080:8080 querymind-frontend:latest
```

`host.docker.internal` resolves to the Windows host from inside a container on Docker Desktop —
useful for pointing the backend container at a Postgres running directly on the host (as opposed
to `docker compose`'s `db` service, which is reachable by service name instead).

### Volume mounts

Neither image expects a volume for normal operation — the backend is stateless (all state lives
in Postgres, run separately) and the frontend serves a static build baked into the image at
build time. The one case a mount is useful:

```bash
# Point the backend at a local .env without baking it into the image or using --env-file's
# flattened single-file limitation, e.g. testing an alternate config directory:
docker run --rm -p 8000:8000 -v "$(pwd)/.env:/app/.env:ro" querymind-backend:latest
```

### Environment variables

The backend image supports every variable `Settings` already reads (`src/querymind/core/config.py`,
`.env.example`) — nothing new was introduced except `APP_PORT`'s new role in also controlling the
container's listen port (it already existed as a `Settings` field; it previously had no effect on
what port `uvicorn` actually bound to). No default is set for `POSTGRES_PASSWORD` or `LLM_API_KEY`
in the image — `Settings` fails fast at startup if a required one is missing, in a container
exactly as it does locally.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `APP_PORT` | no | `8000` | Backend listen port (`EXPOSE`, `HEALTHCHECK`, and `uvicorn --port` all read this) |
| `APP_HOST` | no | `0.0.0.0` | Backend bind address |
| `POSTGRES_USER` | yes | — | Database user |
| `POSTGRES_PASSWORD` | yes | — | Database password (secret) |
| `POSTGRES_DB` | yes | — | Database name |
| `POSTGRES_HOST` | no | `localhost` | Database host — set to `db` under Compose, or a reachable host otherwise |
| `POSTGRES_PORT` | no | `5432` | Database port |
| `LLM_API_KEY` | no | *(empty)* | Anthropic API key (secret) — empty means "LLM not configured," not a startup failure |

See `.env.example` for the complete list (logging, SQLAlchemy pool tuning, LLM generation
parameters) — every one of them already works unchanged inside the container.

The frontend image takes no runtime environment variables: `VITE_*` variables
(`services/api.ts`, `services/streaming.ts`) are Vite build-time values, baked into the static
bundle at `docker build` time, not read at container start. This is deliberately never needed
under Compose — both default to same-origin, relative paths (`/api/v1`, `/ws/query`), which is
exactly what `frontend/nginx.conf`'s proxy blocks now serve; see `frontend/README.md`.

## Health checks

- **Backend**: `HEALTHCHECK` polls `GET http://localhost:${APP_PORT}/api/v1/health/live`
  (`querymind.api.routers.health`'s liveness endpoint — no database round trip, just "is the
  process up") every 30s, 5s timeout, 3 retries, 10s start period.
- **Frontend**: `HEALTHCHECK` polls `GET http://127.0.0.1:8080/` (nginx serving `index.html` --
  `127.0.0.1`, not `localhost`; see the Troubleshooting entry below) every 30s, 5s timeout, 3
  retries, 5s start period. `docker-compose.yml` sets the same check explicitly at the service
  level, for parity with `db`/`app` and visibility in `docker compose ps` without needing to
  inspect the image.

Check a running container's status with `docker inspect --format='{{.State.Health.Status}}' <container>`.

## Security decisions

- **Non-root**: the backend runs as a dedicated system user (`app`); the frontend runs as the
  `nginxinc/nginx-unprivileged` image's built-in non-root `nginx` user, which is also why it
  listens on `8080` rather than `80` — binding a port below 1024 requires root, which this image
  deliberately never has.
- **No secrets in the image**: `POSTGRES_PASSWORD` and `LLM_API_KEY` are never set as `ENV`
  defaults or copied in as a baked-in `.env` file — both images expect them at `docker run`/
  `docker compose` time only, via `-e`/`--env-file`/Compose's `env_file:`, exactly matching how
  local (non-Docker) development already supplies them.
- **Minimal runtime surface**: both runtime stages contain only what's needed to run — no `uv`,
  no `npm`, no compiler, no source tree beyond the compiled artifact, no dev dependencies
  (`--no-dev` in the backend's `uv sync`; `npm ci` installs devDependencies only in the *builder*
  stage, which never ships).

## Troubleshooting

**Backend container exits immediately with a `Settings` validation error.**
A required environment variable (`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`) wasn't
supplied. Check `docker logs <container>` — `Settings` fails fast with a specific, named field
error, not a generic crash.

**Backend can't reach Postgres (`DatabaseConnectionError` / connection refused).**
`POSTGRES_HOST=localhost` (the default, meant for non-Docker local development) doesn't resolve
to anything reachable from inside a container. Use `host.docker.internal` (Docker Desktop) to
reach a Postgres running on the Windows host, or the Compose service name (`db`) if run under
`docker compose`.

**`docker build -f Dockerfile.backend .` fails on `COPY uv.lock` / `pyproject.toml`.**
Build from the repository root, not from inside a subdirectory — the command in this doc's
"Build commands" section already does this (`-t querymind-backend:latest .`, trailing `.` is the
repo root as build context).

**Frontend container serves a blank page or 404s on a direct route (e.g. `/metrics`).**
Confirms the image built without the SPA fallback — check that `nginx.conf`'s `location /`
`try_files $uri $uri/ /index.html;` line made it into the image
(`docker exec <container> cat /etc/nginx/conf.d/default.conf`). A plain `docker run` of this
image (no Compose network) serves the app shell correctly on every route; only the proxied
`/api/*`, `/api/v1/query/stream`, and `/ws/*` routes need a reachable `app` (see `frontend/nginx.conf`).

**Frontend health check fails but the container looks fine in `docker logs`.**
The unprivileged nginx image has no `curl`; the `HEALTHCHECK` uses `wget` (present via BusyBox on
Alpine). If you've modified the base image, confirm `wget` is still on `PATH`.

**Frontend `HEALTHCHECK`/`wget` fails with "Connection refused" even though `netstat -tln`
inside the container shows nginx listening on `0.0.0.0:8080`.**
Fixed as of the Phase 19A healthcheck follow-up — `wget http://localhost:8080/` resolved
`localhost` to `::1` (IPv6) via the image's `/etc/hosts` and Alpine musl's RFC 6724 address
preference, which nginx (IPv4-only `listen 8080;`) was never listening on. The `HEALTHCHECK`
(and `docker-compose.yml`'s service-level check) now target `127.0.0.1` explicitly. If you see
this again after modifying `frontend/Dockerfile` or `docker-compose.yml`, confirm neither
reintroduced a bare `localhost`.

**`docker compose up` starts `frontend` before `app` is actually ready, and proxied requests
502 for a few seconds.**
Confirm `docker-compose.yml`'s `frontend` service still has `depends_on: app: condition:
service_healthy`, not just `depends_on: [app]` (which only waits for the container to start,
not for `app`'s own healthcheck to pass) — `condition: service_healthy` is what makes nginx's
`resolver`-based proxy_pass reliably find `app` already listening on the shared network.

**`docker run --env-file .env` fails at startup with a `Settings` "literal_error" on `app_env`/`log_format`.**
`.env`/`.env.example` are written for `python-dotenv` (via `pydantic-settings`'s `env_file=".env"`),
which strips trailing inline comments (`APP_ENV=development   # development | staging | ...`) —
but Docker's own `--env-file` parser does not; it treats everything after `=` as the literal
value, comment included, which then fails `Settings`' `Literal[...]` validation. This is a real
format mismatch between the two loaders, not a Phase 19A regression. Workaround: pass the
affected variables explicitly with `-e` instead of relying on `--env-file` for them (as this
doc's own "Run commands" `-e` example already does), or strip inline comments from a copy of
`.env` before using it with `--env-file`. Verified end-to-end this way: the backend image starts,
connects to a real PostgreSQL instance, and serves `GET /api/v1/health/live` and
`GET /api/v1/settings` correctly.

**Windows-specific: Docker Desktop.**
Both images were built and run against Docker Desktop on Windows (WSL2 backend) for this phase.
No Linux-only assumptions are made (no bind-mounted Unix sockets, no `host.docker.internal`
absence workarounds needed) — `docker build`/`docker run` work identically to any other
Docker Desktop host.