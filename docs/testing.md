# Testing

## Test philosophy

Every phase in this codebase follows the same two-tier testing strategy:
fast, isolated unit tests for a phase's own logic, and a small number of
real, fully-wired integration tests that exercise the actual production
path. Both tiers avoid mocking anything beyond the one genuinely external
dependency (the LLM's network call) — real Pydantic models, real
registries built from the project's own shipped data, and a real
PostgreSQL database are all preferred over hand-rolled test doubles
wherever practical.

As of the current test suite: **1068 tests passing**, **78% statement
coverage** across `src/querymind` (`uv run pytest` reports the exact,
current numbers — treat any number here as a snapshot, not a promise).

## Unit tests

Each phase's `test_<module>.py` files test one collaborator in isolation
— `ValueFormatter`, `ExecutionGuard`, `RepairPlanner`, and so on — using
real, minimally constructed model instances built by that phase's
`conftest.py` builder functions (`make_<model>(**overrides)`), never a
mock of a Pydantic model.

A phase's own `test_engine.py` is the one place fakes are used: small,
hand-written classes implementing just the one method the real
collaborator exposes (e.g. a `_FakeExecutor` with only an `execute()`
method), configured to return a canned result or raise a specific
exception. This tests the *engine's own orchestration logic* — does it
call its collaborators in the right order, does it convert the right
exception into the right result — without depending on any collaborator's
own internal correctness, which that collaborator's own tests already
cover. `tests/orchestrator/test_pipeline.py` is the largest example of
this pattern: all ten of `PipelineRunner`'s phase-engine collaborators are
faked, so its tests can assert on sequencing and branching (is repair
skipped when validation passes, does a stage's own exception carry the
right partial timings) in milliseconds, with no database and no network
anywhere in the file.

## Integration tests

Each phase's `test_integration.py` wires the *real* phase — its real
collaborators, not fakes — against real, shared data:

- `metadata_registry`, `business_knowledge_registry`, and `query_library`
  fixtures are session-scoped and built from the project's own shipped
  schema and YAML-sourced catalogs, not a hand-rolled fake schema. A test
  failure here means something real about how the phase behaves against
  this project's actual data.
- Any phase that touches the database (`sql_execution` onward) uses a
  real, already-running PostgreSQL instance via `DatabaseConnectionProvider`
  built from the same `Settings`/`create_engine` the application itself
  uses.
- Any phase that would otherwise call the LLM replaces only the network
  transport with `httpx.MockTransport` — the real `LLMAdapter`,
  `ClaudeProvider`, retry policy, and response parser all still run;
  nothing about the LLM call itself is faked, only the socket.

`tests/orchestrator/test_integration.py` is the broadest example: it
builds every one of the ten real phase engines (real schema linker, real
retrieval engine, real prompt compiler, real validation engine, real
repair engine, real execution engine against the real database, real
result formatter) and drives the complete pipeline through
`QueryMindEngine.ask()` for a real question, asserting that the repair
path is skipped when generated SQL validates on the first attempt, that
repair is invoked (and its output reused, never re-validated manually)
when it doesn't, that every expected `PipelineStage` timing is present,
and that the final `BusinessAnswer`'s rows match the real
`SQLExecutionResult`'s rows exactly.

## Mock transport

The only component ever mocked anywhere in this test suite is the LLM's
HTTP transport. Every LLM-touching integration test builds a real
`LLMAdapter`/`ClaudeProvider` pair with `httpx.Client(transport=
httpx.MockTransport(handler))`, where `handler` is a small function
returning a scripted `httpx.Response` shaped like a real Claude API
response. This means retry logic, timeout handling, and response parsing
are exercised for real — only the actual network socket is replaced —
and no test suite run ever makes a real API call or requires an API key.

`sequential_sql_handler` (in several phases' `conftest.py` files,
including `tests/orchestrator/conftest.py`) scripts a sequence of
responses returned one per call, which is how the repair-path integration
tests simulate "the LLM's first attempt is broken SQL, its second attempt
is the fix" without any real model call.

## Real PostgreSQL tests

Starting with `sql_execution` (Phase 13), tests genuinely execute SQL
against a real, already-running PostgreSQL instance rather than mocking
the database layer — `AsyncConnection`/`AsyncEngine` have no meaningful
public seam worth faking, and the behavior under test (read-only
enforcement, real connection-failure translation, real query execution)
is only meaningful against a real database. Each test file's `engine`
fixture is **function-scoped, not session-scoped** — an `AsyncEngine`'s
connection pool holds event-loop-bound asyncio primitives, and this
project gives each async test its own event loop
(`pytest-asyncio`'s `asyncio_mode = "auto"` default), so a session-scoped
engine built in one test's loop breaks when a later test's loop tries to
reuse it. This was discovered empirically during Phase 13 development
(`RuntimeError: Event loop is closed`) and the function-scoped fixture
pattern has been used in every phase's `conftest.py` since.

Running the suite requires a reachable PostgreSQL instance — see
[`getting-started.md`](getting-started.md#3-create-the-database). No
seeded data is required for most database-touching tests (they query
`customers`/`orders`/etc. structurally or insert nothing), but a migrated,
empty-or-seeded schema must exist.

## Coverage expectations

`pytest-cov` runs on every `pytest` invocation by default
(`--cov=src/querymind --cov-report=term-missing`, configured in
`pyproject.toml`). There is no hard-enforced minimum threshold in CI
configuration today — coverage is reviewed per phase at the time it's
built, not gated automatically. In practice, every phase built since
Phase 5 has near-complete coverage of its own package; the current
whole-repository figure (78%, 1068 tests) reflects that most gaps are in
older infrastructure (`seeds/`, `api/`) rather than the text-to-SQL
pipeline itself. Treat a coverage *decrease* on a touched file as a signal
worth investigating, not an automatic build failure.
