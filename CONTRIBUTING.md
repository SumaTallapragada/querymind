# Contributing to QueryMind

This document describes the conventions this codebase actually follows.
If you're adding a new phase or extending an existing one, matching these
conventions is more important than any individual line of code — every
phase in this repository follows the same shape, and a new one that
doesn't will stand out immediately in review.

## Toolchain

| Tool | Version / config | Command |
|---|---|---|
| Python | 3.12 (`requires-python = ">=3.12,<3.13"`) | — |
| [uv](https://docs.astral.sh/uv/) | dependency management | `uv sync`, `uv run <cmd>` |
| Ruff | lint + format | `uv run ruff check .`, `uv run ruff format .` |
| MyPy | `strict = true` | `uv run mypy src` |
| pytest | + `pytest-asyncio` (`asyncio_mode = "auto"`), `pytest-cov` | `uv run pytest` |

All four are configured in `pyproject.toml` — there is no separate lint or
type-check config file. `make check` runs lint + typecheck + test as one
gate; run it (or the three commands individually) before opening a PR.

### uv

Every command in this repository is expected to run through `uv run` (or
inside a shell where `uv sync` has already built `.venv`), not a bare
`python`/`pip` invocation. Add a new dependency with `uv add <package>`
(runtime) or `uv add --dev <package>` (dev-only); do not hand-edit
`pyproject.toml`'s dependency lists or `uv.lock` directly.

### Ruff

The selected rule set (see `[tool.ruff.lint]` in `pyproject.toml`) is
`E`/`W`/`F`/`I`/`UP`/`B`/`C4`/`SIM`/`N`/`ASYNC`/`RUF`/`TID`/`PT`. Line
length is enforced by the formatter (`line-length = 100`), not the linter
(`E501` is explicitly ignored). Don't add `# noqa` comments for rules that
aren't actually selected — check `[tool.ruff.lint.select]` first; an
unused `# noqa` is itself a lint error (`RUF100`) under this config.

### MyPy

`strict = true`, plus `disallow_untyped_defs`, `disallow_any_generics`,
`warn_redundant_casts`, `warn_unused_ignores`, `warn_return_any`, and
`no_implicit_reexport`. `tests.*` has one relaxation
(`disallow_untyped_defs = false`) — test *bodies* don't need every local
annotated, but public functions (fixtures, builder helpers) in test
`conftest.py` files should still be typed, matching existing test code.
`pydantic.mypy` is enabled with `init_forbid_extra = true` and
`init_typed = true` — every Pydantic model constructor call is checked as
strictly as a regular function call.

### pytest

`asyncio_mode = "auto"` — async test functions and async fixtures need no
special marker or decorator, just `async def`. `filterwarnings = ["error"]`
— any warning raised during a test run fails that test; don't add a broad
warning filter to work around one, fix what's raising it (or, if it's
unavoidable and genuinely benign, filter that *specific* warning by name).
Coverage (`--cov=src/querymind --cov-report=term-missing`) runs on every
`pytest` invocation by default.

## Coding conventions

- **Docstrings explain *why*, not *what*.** A well-named function doesn't
  need a docstring restating its name in prose. Every module and every
  non-trivial class in this codebase has a docstring — but it exists to
  record a non-obvious constraint, a rejected alternative, or a subtlety a
  future reader would otherwise have to rediscover from scratch (see any
  existing `engine.py` for the pattern).
- **No dead code, no speculative abstraction.** Don't add a parameter,
  branch, or helper for a case nothing in this codebase actually
  exercises. Three similar lines are better than a premature abstraction.
- **Reuse across phases only through a phase's public `__init__.py`
  exports.** Never import another phase's private, non-exported class or
  function. If two phases need the same small, stable piece of data (e.g.
  a `SQLDialect → sqlglot dialect string` mapping), duplicating it in both
  places is the established pattern in this codebase — it is preferred
  over importing a private symbol across a package boundary.
- **A phase never reaches backward.** A later phase may import an earlier
  phase's public models (e.g. `sql_execution` imports
  `sql_generation.GeneratedSQL`), but an earlier phase must never import
  from a later one.

## Naming conventions

- **Packages** are lowercase, `snake_case`, and named after the phase's
  domain concept, not a generic word (`sql_validation`, not `validation`).
- **The one public orchestration class per phase** is named
  `<Domain><Role>`, where `Role` is `Engine` (`SQLValidationEngine`),
  `Registry` (`MetadataRegistry`, `BusinessKnowledgeRegistry`), or a
  concrete verb-noun (`SchemaLinker`, `QueryParser`, `PromptCompiler`,
  `LLMAdapter`). The composition root is `QueryMindEngine`.
- **Single-responsibility collaborators** are named for exactly what they
  do: `ValueFormatter`, `ExecutionGuard`, `RepairPlanner`,
  `PipelineStatisticsBuilder`. Avoid generic names like `Helper`,
  `Manager`, or `Utils`.
- **Models** are named for the artifact they represent, not the phase that
  produced it: `GeneratedSQL`, not `SQLGenerationOutput`;
  `SQLValidationResult`, not `ValidationOutput`.
- **Exceptions** form a per-phase hierarchy rooted at `<Domain>Error`
  (`SQLRepairError`, `ResultFormatterError`, `QueryMindError`), with
  specific subclasses named for the exact failure
  (`ExecutionRejectedError`, `SummaryGenerationError`).
- **Cache types** are always a `Protocol` named `<Domain>Cache` plus a
  `NoOp<Domain>Cache` that satisfies it without caching anything — every
  phase from `prompt_compiler` onward follows this exact pair, even though
  most are not yet wired up (see
  [`docs/architecture-decisions.md`](docs/architecture-decisions.md)).

## Dependency Injection rules

- **Constructor injection only.** No global state, no singleton service,
  no service locator, anywhere in the pipeline packages (`core.config
  .get_settings`'s `lru_cache` is the one deliberate exception, scoped
  narrowly to application configuration — see
  [`docs/architecture-decisions.md`](docs/architecture-decisions.md)).
- **Required dependencies have no default.** If a class cannot function
  without something only the caller can provide (a real registry, a real
  database connection provider, a real LLM adapter), that parameter is
  required, with no `= None` fallback.
- **Optional collaborators default to the standard implementation.** A
  class's own internal, replaceable collaborators are typed
  `Collaborator | None = None` and constructed with a sensible default
  inside `__init__` when omitted — never a mutable default argument, never
  built lazily on first use.

## Immutability rules

- Every model that is returned from a public method or crosses a phase
  boundary is a Pydantic v2 model with `model_config = ConfigDict(frozen=True,
  extra="forbid")`.
- Every collection field on such a model is a `tuple`, never a `list` —
  a frozen Pydantic model still allows in-place mutation of a `list`
  field; a `tuple` field does not.
- A phase that needs to "modify" something it received always constructs
  a *new* immutable model instead — never call `object.__setattr__` to
  bypass frozen-ness, and never `.model_copy(update=...)` to quietly patch
  a value a downstream consumer expects to trace back to its origin
  (prefer building a fresh, explicit model).

## Folder organization

Every phase package follows the same internal shape:

```
src/querymind/<phase>/
    __init__.py       # public surface only — every name in __all__
    models.py          # every model this phase produces (or consumes and re-exports)
    engine.py           # the phase's single public entry point, orchestration only
    exceptions.py         # <Phase>Error hierarchy
    cache.py             # <Phase>Cache Protocol + NoOp<Phase>Cache
    serializer.py          # dict/JSON/YAML export of this phase's result model
    <collaborator>.py, ...   # one file per single-responsibility collaborator

tests/<phase>/
    conftest.py          # fixtures + synthetic model builders for this phase
    test_models.py
    test_<collaborator>.py, ...
    test_engine.py         # orchestration logic, collaborators faked
    test_integration.py      # the real, fully-wired phase (or pipeline) — no fakes
```

A new phase's `engine.py` should read like every existing one: a class
whose constructor takes its collaborators (each defaulted where sensible)
and whose one public method sequences calls into them, with no business
logic of its own.

## How to add a new phase

1. Read every phase this new one will consume, starting from its
   `__init__.py` docstring and `__all__` — never guess at another phase's
   API.
2. Create `src/querymind/<phase>/` following the folder shape above.
   Start with `exceptions.py` and `models.py` — every other file will
   reference them.
3. Write each single-responsibility collaborator as its own file and
   class, then `engine.py` to sequence them. If you find yourself writing
   business logic directly in `engine.py`, it almost certainly belongs in
   a dedicated collaborator instead.
4. Write `cache.py` (`Protocol` + `NoOp` implementation) and
   `serializer.py` (`to_dict`/`to_json`/`to_yaml`) even if nothing wires
   them up yet — every existing phase does, for consistency and so a
   future phase can adopt real caching without changing this phase's
   shape.
5. Export the complete public surface from `__init__.py` with an
   `__all__` list, matching the style of any existing phase's
   `__init__.py`.
6. Run `uv run ruff format .`, `uv run ruff check . --fix`, and
   `uv run mypy src/querymind/<phase>` before writing tests — catching
   type errors early is much cheaper than after the test suite is built
   around them.

## How to add tests

- Mirror the source package's file layout: one `test_<module>.py` per
  `<module>.py`.
- `conftest.py` holds fixtures and synthetic model builders
  (`make_<model_name>(**overrides)` functions returning a minimal, valid
  instance with sensible defaults) — follow the existing pattern in any
  phase's `tests/<phase>/conftest.py` rather than inventing a new one.
- Unit-test a phase's own orchestration logic (`test_engine.py`) with
  small, scripted fake collaborators (a class implementing just the one
  method the real collaborator exposes) — never assert on another phase's
  internal correctness through a fake; that phase's own test suite already
  covers it.
- `test_integration.py` uses the real, fully-wired phase (or, for
  `orchestrator`, the real, fully-wired *pipeline*): real registries built
  from the project's own shipped schema/business data, a real database
  connection where the phase touches the database, and
  `httpx.MockTransport` in place of the real LLM network call — never a
  live network call in any test. See
  [`docs/testing.md`](docs/testing.md) for the full rationale.
- Run the new phase's suite in isolation first
  (`uv run pytest tests/<phase> -q`), then the whole repository
  (`uv run pytest -q`) to confirm zero regressions before committing.
