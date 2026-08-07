# CI/CD (Phase 19D)

GitHub Actions workflows for QueryMind. Five workflows, two tiers: **Fast CI** (lint/type/unit
tests/builds, on every push and PR) and a **heavy Integration workflow** (the real-PostgreSQL
suite against the actual `docker-compose.yml` stack, on demand/nightly/release tags only). A
**Release** workflow builds and archives versioned artifacts and prepares a draft GitHub Release.

## Folder structure

```
.github/
└── workflows/
    ├── backend.yml       Fast CI: Ruff, Ruff format, MyPy, unit tests, backend image build
    ├── frontend.yml      Fast CI: oxlint, tsc, Vitest, Vite build, frontend image build
    ├── docker.yml        Fast CI: both images build + `docker compose config`
    ├── integration.yml   Heavy tier: real Postgres + live docker-compose.yml stack
    └── release.yml       Build, archive, and draft-release both images + the frontend build
```

This matches the structure this phase's brief suggested, unmodified — one file per concern
(`backend`/`frontend`/`docker` split, rather than one monolithic `ci.yml`) so each shows up as
its own status check, and `integration`/`release` are separate because they trigger completely
differently from the other three (see below).

## The two-tier strategy

| | Fast CI (`backend.yml`, `frontend.yml`, `docker.yml`) | Integration (`integration.yml`) |
|---|---|---|
| Triggers | every `push`, every `pull_request` | `workflow_dispatch`, nightly `schedule`, `push` of a `v*` tag |
| Starts PostgreSQL? | No | Yes (`docker compose up`) |
| Runs `docker compose up`? | No (`docker compose config` only) | Yes, the full stack |
| Typical duration | ~1–2 minutes each, in parallel | several minutes (real infra) |
| What it proves | the code is correct in isolation | the *system*, wired together with a real database, actually works |

Fast CI never touches a real database and never starts a container beyond a throwaway `docker
build`. The `tests/**/test_integration.py` suite (and a handful of individually DB-dependent
tests living inside otherwise-hermetic files — see `backend.yml`'s own comments for the exact,
verified list) are excluded via `--ignore-glob`/`--deselect`, not by any change to test source —
this codebase has no pytest markers, and adding any would be a test-source change, out of scope
for a CI-only phase. Every excluded test still runs, for real, in `integration.yml`.

## Running workflows manually

All five workflows can be triggered from the Actions tab (**Actions → \<workflow name\> → Run
workflow**) or via the GitHub CLI:

```bash
gh workflow run backend.yml
gh workflow run frontend.yml
gh workflow run docker.yml
gh workflow run integration.yml
gh workflow run release.yml -f version=v1.2.0-rc1   # workflow_dispatch takes a version input
```

`backend.yml`/`frontend.yml` also accept `workflow_call` (used by `release.yml` to gate a
release on them passing, without re-implementing their steps) alongside their normal
`push`/`pull_request` triggers — both trigger types are always active at once.

## Required GitHub Secrets

Only `integration.yml` and `release.yml` (via `GITHUB_TOKEN`, automatic) need secrets. Fast CI
needs none — it never starts real infrastructure.

| Secret | Used by | Required? | Notes |
| --- | --- | --- | --- |
| `POSTGRES_USER` | `integration.yml` | no | Falls back to `querymind` if unset |
| `POSTGRES_PASSWORD` | `integration.yml` | recommended | Falls back to a CI-only placeholder if unset — set a real value so this doesn't silently run with a throwaway password |
| `POSTGRES_DB` | `integration.yml` | no | Falls back to `querymind` if unset |
| `LLM_API_KEY` | `integration.yml` | no | If unset, the live-stack SSE/WebSocket checks still pass (they only assert a `pipeline_started` frame arrives, not that the LLM call itself succeeds); pytest's own integration suite mocks the LLM transport regardless and needs no key either way |

Set these under **Settings → Secrets and variables → Actions → New repository secret**.
`release.yml`'s draft-release step uses the automatically-provided `GITHUB_TOKEN` (scoped via
the job's `permissions: contents: write`) — no separate secret needed. There is no container
registry credential yet (see "Not implemented yet" below) — nothing pushes an image anywhere.

Every secret value GitHub Actions injects is automatically masked in logs (replaced with `***`
if it would otherwise be printed); none of these workflows additionally `echo`/`cat` a secret
value, as defense in depth beyond that automatic masking.

## Workflow details

### `backend.yml` — Fast CI

Two parallel jobs: `lint-typecheck-test` (Ruff → Ruff format check → MyPy → the excluded-integration
unit suite, all via `uv run`) and `docker-build` (builds `Dockerfile.backend`, not pushed). Uses
`astral-sh/setup-uv` with `enable-cache: true`, keyed on `uv.lock`'s hash.

### `frontend.yml` — Fast CI

Two parallel jobs: `lint-typecheck-test-build` (oxlint → tsc → Vitest → Vite build, all via
`npm run`, with `npm ci` from the lockfile) and `docker-build` (builds `frontend/Dockerfile`,
not pushed). `actions/setup-node`'s built-in `cache: npm` handles npm's cache. The build job also
uploads `frontend/dist` as a workflow artifact (`frontend-dist`) — not for Fast CI's own sake,
but so `release.yml` can reuse the exact same build without rebuilding it.

### `docker.yml` — Fast CI

Deliberately separate from the two above so there's one specific, language-agnostic status
check for "the Docker infra itself is intact": builds both images again (sharing the same
`type=gha` Buildx cache scope as `backend.yml`/`frontend.yml`, so the duplication is cheap) and
runs `docker compose config --quiet` against a placeholder `.env` (non-secret dummy values,
committed directly in the workflow — needed only so Compose can interpolate `${POSTGRES_USER}`
etc. to validate the file's syntax; nothing is ever started). Never runs `docker compose up`.

### `integration.yml` — heavy tier

1. Writes a real `.env` from GitHub Secrets.
2. `docker compose up -d --build` — the actual stack, `db` → `app` → `frontend`.
3. Three explicit wait steps (not just relying on Compose's own `depends_on` gating): PostgreSQL
   healthy, backend healthy *and* answering `GET /api/v1/health`, frontend healthy *and* serving.
4. `uv run pytest -q` — the **full** suite, no exclusions, run on the runner directly against
   the stack's published Postgres port (mirrors how local development already runs `uv run
   pytest` against a `docker compose`-provisioned database).
5. Networking validation: confirms `GET /api/v1/health` returns byte-identical output whether
   requested directly (`:8000`) or through the frontend's reverse proxy (`:8080`).
6. SSE validation: confirms a `pipeline_started` frame arrives from `POST /api/v1/query/stream`
   through the proxy.
7. WebSocket validation: a small inline Python client confirms a `pipeline_started` frame
   arrives from `/ws/query` through the proxy.
8. On failure only: `docker compose logs` captured and uploaded as an artifact.
9. Always: `docker compose down -v` (this run's seeded data is disposable).

### `release.yml`

`push` of a `v*` tag, or `workflow_dispatch` with a `version` input for a dry run. Calls
`backend.yml`/`frontend.yml` as reusable workflows first (`uses: ./.github/workflows/....yml`) —
a release is gated on Fast CI passing, without re-implementing its steps. Then builds both images
tagged with the resolved version, archives them (`docker save | gzip`) alongside the frontend's
static build (downloaded from `frontend.yml`'s `frontend-dist` artifact, not rebuilt), uploads
everything as a workflow artifact, and creates a **draft** GitHub Release (`draft: true`) with
those files attached and auto-generated release notes. Never auto-published — a maintainer
reviews and publishes it by hand, per this phase's explicit scope.

**Not implemented yet** (intentionally, per Phase 19D's scope): pushing either image to a
container registry. `docker/build-push-action`'s `push:` is `false` everywhere in every
workflow; images only ever exist locally within a single job (`load: true` in `release.yml`,
solely so `docker save` can archive them) or as GitHub Actions build cache. Wiring up a real
registry (and the credential secret that implies) is deployment scope, later than this phase.

## Caching strategy

| Dependency | Mechanism |
| --- | --- |
| `uv` (Python packages) | `astral-sh/setup-uv`'s `enable-cache: true`, keyed on `uv.lock` |
| `npm` | `actions/setup-node`'s built-in `cache: npm`, keyed on `frontend/package-lock.json` |
| Docker layers | `docker/build-push-action`'s `cache-from`/`cache-to: type=gha`, one scope per image (`backend`/`frontend`), shared across `backend.yml`/`frontend.yml`/`docker.yml`/`release.yml` |

## Security considerations

- No secret is ever hardcoded in a workflow file — only `${{ secrets.* }}` references, all in
  `integration.yml` (the only workflow that needs any).
- GitHub Actions masks known secret values in logs automatically; no workflow additionally
  prints one.
- Fast CI (`backend.yml`, `frontend.yml`, `docker.yml`) needs zero secrets and starts no real
  infrastructure — safe to run against a fork's pull request with no special configuration.
- `release.yml`'s only elevated permission is `contents: write`, scoped to the one job that
  creates the draft release, following least-privilege (every other job in every workflow has
  the default, read-only `GITHUB_TOKEN` permissions).
- No image is ever pushed anywhere; nothing here can leak a credential to a registry because no
  registry credential exists yet.

## Local reproduction

Every Fast CI step is exactly the command a developer already runs locally (see the root
`Makefile` and `frontend/package.json`) — `uv run ruff check .`, `uv run mypy src`, `npm run
lint`, etc. — plus the specific unit-test-selection command documented in `backend.yml`, which
can be copied and run locally verbatim to reproduce Fast CI's backend test step exactly. For the
Integration workflow, `docker compose up -d --build` followed by `uv run pytest -q` (see
`docs/docker.md`) reproduces it locally, against a real database, before ever pushing.