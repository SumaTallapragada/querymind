# Release Checklist — QueryMind Core Engine v1.0

Status as of the Phase 15.5 stabilization pass. Re-run the verification
commands before actually tagging a release — this snapshot reflects one
point-in-time run, not a continuously enforced gate.

## Code quality

- [x] **Ruff (lint)** — `uv run ruff check .` → all checks passed.
- [x] **Ruff (format)** — `uv run ruff format --check .` → all files
      already formatted (379 files).
- [x] **MyPy (strict)** — `uv run mypy src` → no issues in 217 source
      files.
- [x] **Pytest** — `uv run pytest -q` → 1,068 passed, 0 failed, 0 skipped.
- [x] **Coverage** — 78% statement coverage across `src/querymind`
      (`--cov-report=term-missing`, configured in `pyproject.toml`). No
      hard minimum threshold is enforced in CI configuration — see
      [`docs/testing.md`](docs/testing.md#coverage-expectations).

## Documentation

- [x] **README.md** — reflects the actual current pipeline (11 stages),
      accurate installation/setup/testing instructions, correct roadmap
      (REST API explicitly not yet implemented).
- [x] **ARCHITECTURE.md** — layering, dependency direction, every
      package's responsibility, all present and verified against the
      actual dependency graph (programmatic check, zero violations).
- [x] **SYSTEM_DESIGN.md** — every cross-phase model documented, "why
      this phase exists" for all 11 stages.
- [x] **CONTRIBUTING.md** — toolchain, conventions, DI/immutability
      rules, "how to add a phase"/"how to add tests" present.
- [x] **docs/** — `getting-started.md`, `project-structure.md`,
      `pipeline.md`, `architecture-decisions.md`, `testing.md`,
      `glossary.md`, `KNOWN_LIMITATIONS.md` all present.
- [x] **Internal links/anchors** — every markdown link and heading anchor
      across the repository verified programmatically; zero broken.
- [x] **No invented functionality** — documentation describes only what
      is implemented; deferred work is listed under "roadmap"/"known
      limitations," not described as present.

## Dependency audit

- [x] **`uv.lock` in sync with `pyproject.toml`** — `uv lock --check`
      passes.
- [x] **No unused runtime dependencies found** — every declared
      dependency is either directly imported or a verified indirect
      runtime requirement (`asyncpg` via SQLAlchemy's async dialect,
      `python-dotenv` via `pydantic-settings`' `env_file` support,
      `uvicorn` as the ASGI process). See the Dependency Audit in the
      Phase 15.5 deliverable for full detail.
- [x] **No duplicate/conflicting transitive dependencies** — reviewed via
      `uv tree` (50 resolved packages).
- [ ] **Version ceiling refresh** — not performed this release; several
      pinned upper bounds (`ruff<0.8.0`, `ecosystem-current fastapi/pydantic
      ranges, etc.) were set during initial development and have not been
      revisited. Flagged as a recommendation for a future maintenance
      pass, not a release blocker.

## Architecture audit

- [x] **Dependency direction** — verified programmatically: zero
      instances of an earlier-phase package importing a later-phase
      package.
- [x] **No circular imports** — verified by importing all 19 top-level
      packages in isolation; all succeed.
- [x] **Constructor dependency injection preserved** — spot-checked
      across all 14 pipeline packages; no new global state or singleton
      introduced.
- [x] **Immutable models preserved** — no `frozen=True`/`extra="forbid"`
      model relaxed; no `list` field introduced on a cross-phase model.
- [x] **Public API surfaces unchanged** — every package's `__all__`
      reviewed; no accidental export added or removed (see Public API
      Audit).
- [ ] **Two documented cross-package boundary gaps** — not fixed this
      release, per this phase's "document, don't redesign" rule. See
      [`docs/architecture-decisions.md`](docs/architecture-decisions.md#known-gaps).

## Release artifacts

- [x] **CHANGELOG.md** — created, documents all completed phases and
      Phase 15.5 findings.
- [x] **VERSION** — created, contains `1.0.0`.
- [x] **VERSION_HISTORY.md** — created, phase-by-phase narrative.
- [x] **docs/KNOWN_LIMITATIONS.md** — created.
- [ ] **License** — `pyproject.toml` still declares `license = { text =
      "Proprietary" }` as a placeholder; no formal license has been
      selected. **Release blocker if this is intended for public/open-source
      distribution** — resolve before any public release.
- [x] **Version bumped** — `pyproject.toml` and `uv.lock` updated from
      `0.1.0` to `1.0.0` to match this release.
- [ ] **Git tag** — not created as part of this stabilization pass (no
      git tag operation was performed). Create `v1.0.0` once this work is
      reviewed and merged.
- [ ] **Phase 15 (`orchestrator`) committed** — `src/querymind/orchestrator/`
      and `tests/orchestrator/` were present but uncommitted as of this
      audit; confirm they (and this stabilization pass's changes) are
      committed before tagging.

## Sign-off

This checklist reflects a **release-candidate** state: code quality,
tests, and documentation are verified and consistent; the license
placeholder and git tagging are the two items still requiring an explicit
decision/action before an actual public release.
