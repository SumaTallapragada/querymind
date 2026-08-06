# Architecture Decision Records

This document records the significant, project-wide architectural
decisions behind QueryMind, in the lightweight ADR format (Context /
Decision / Consequences). These are decisions that shaped every phase, not
implementation details local to one package — those are documented inline
in the relevant module's docstring.

---

## ADR 1 — Every cross-phase model is immutable

**Context.** The pipeline is a strict, one-directional chain: each phase
receives the previous phase's output and produces a new artifact for the
next. A later phase (e.g. `sql_repair`) must never be able to alter what
an earlier phase (`sql_validation`) already reported, even by accident,
because the orchestrator and any caller need to trust that
`SQLValidationResult.is_valid` still means what it meant when validation
produced it.

**Decision.** Every model that crosses a phase boundary is a Pydantic v2
model with `model_config = ConfigDict(frozen=True, extra="forbid")`, and
every collection field is a `tuple`, never a `list` — a frozen Pydantic
model still permits in-place mutation of a `list` field; a `tuple` field
genuinely cannot be mutated.

**Consequences.** A phase that needs to "modify" something always
constructs a new model instance instead. This is slightly more verbose at
call sites (e.g. `sql_repair` builds an entirely new `GeneratedSQL` per
attempt rather than patching the original) but eliminates an entire class
of bug — aliasing mutation — from the pipeline. `extra="forbid"` is a
second, independent benefit: a typo'd or stale field name in a constructor
call fails immediately, not when some later consumer reads a field that
was silently never set.

---

## ADR 2 — Constructor dependency injection everywhere, no globals, no singletons

**Context.** Every phase engine has real dependencies — a database
connection provider, an LLM adapter, a metadata registry — that differ
between production, tests, and different callers within the same process.

**Decision.** Every dependency is passed through a constructor. There is
no module-level global holding a shared instance, and no service-locator
pattern (`get_thing()` reaching into ambient state) anywhere in the
pipeline packages. Two apply: (1) a class's own fine-grained internal
collaborators default to the standard implementation when the constructor
parameter is omitted (`Collaborator | None = None`); (2) a class's
dependency on something only the caller can construct (a real
`MetadataRegistry`, a real `DatabaseConnectionProvider`) is a required
parameter with no default.

**Consequences.** Every phase is independently testable with fakes,
without any monkeypatching or `unittest.mock` machinery — see
[`testing.md`](testing.md). The one deliberate, narrowly scoped exception
is `core.config.get_settings()`, whose `lru_cache` memoizes a single
process-wide `Settings` instance — a genuine singleton, but one that
represents actual immutable process configuration (read once from the
environment at startup) and is trivially overridden per-test via FastAPI's
`app.dependency_overrides`, not ambient global mutable state.

---

## ADR 3 — Single responsibility, small focused classes

**Context.** Early phases could have been built as one large class per
phase performing every step internally.

**Decision.** Each phase is decomposed into small, single-purpose
collaborators (e.g. `sql_execution` has a separate `ExecutionGuard`,
`DatabaseConnectionProvider`, `SQLExecutor`, and `ResultFormatter`;
`result_formatter` has a separate `ValueFormatter`, `ResultFormatter`,
`SummaryGenerator`, `AnswerGenerator`, and `StatisticsBuilder`), with the
phase's `engine.py` doing nothing but sequencing calls between them.

**Consequences.** Each collaborator is independently unit-testable and
independently replaceable via constructor injection (ADR 2). The tradeoff
is more files per phase and more constructor parameters to wire — accepted
deliberately, since the alternative (one large class per phase) would
concentrate untestable, unsubstitutable logic exactly where the pipeline
most needs it to be inspectable.

---

## ADR 4 — SQL validation is strictly read-only

**Context.** Validation needs to be safe to call as many times as needed
— including by the repair loop, to re-check its own repaired output —
without ever risking a side effect on the SQL it inspects or the database.

**Decision.** `SQLValidationEngine.validate` never modifies the
`GeneratedSQL` it receives and never executes anything against a database
— it parses the SQL text with `sqlglot` and inspects the resulting AST
plus in-memory metadata/business-knowledge registries only.

**Consequences.** Repair (`sql_repair.RepairValidator`) can wrap the exact
same `SQLValidationEngine` to check its own attempts without any special
casing, and the orchestrator never needs to reason about validation having
side effects when deciding whether to call it more than once.

---

## ADR 5 — `sqlglot` as the SQL parser, never regex

**Context.** Multiple phases (validation, repair, execution) need to
inspect SQL structurally: is this a single statement, is it read-only,
does it reference a real table, does it contain an aggregate function.

**Decision.** Every structural SQL check in this codebase parses with
`sqlglot` and inspects the resulting AST — never a regular expression
against the raw SQL text.

**Consequences.** This closed two real gaps discovered during development
of `sql_execution.ExecutionGuard`: `sqlglot.parse_one` silently parses only
the *first* statement of a multi-statement string
(`"SELECT 1; DROP TABLE customers;"` parses as a harmless `SELECT 1`),
so `ExecutionGuard` uses `sqlglot.parse` (the list-returning form) and
requires exactly one statement; and a statement rooted at `Select` can
still contain a write hidden inside a PostgreSQL writable CTE
(`WITH deleted AS (DELETE FROM ... RETURNING *) SELECT * FROM deleted`), so
`ExecutionGuard` walks the *entire* AST for a write node, not just the
root. Both gaps would be far easier to miss with a regex-based check.
(`sql_validation.SyntaxValidator` currently only checks the root node type
— a known, documented, out-of-scope gap in that phase, closed
independently in `ExecutionGuard` rather than silently patched upstream;
see [Known gaps](#known-gaps) below.)

---

## ADR 6 — Prompt compilation is a separate phase from the LLM call

**Context.** Turning structured retrieval data into readable, correctly
budgeted prompt text (section ordering, token-budget trimming, validation)
is a substantial, independent concern from actually calling a model.

**Decision.** `prompt_compiler.PromptCompiler.compile` produces a
`CompiledPrompt` — plain text plus structure — with zero knowledge of any
LLM provider. `llm.LLMAdapter.generate` consumes a `CompiledPrompt` with
zero knowledge of prompt sections, templates, or budgets.

**Consequences.** A different prompt strategy (a new `PromptTemplate`, a
different trimming order) and a different LLM provider are each
independently swappable. It also means `llm` is the *only* package in the
entire pipeline that performs network I/O — every other phase, including
ones that trigger it indirectly (`sql_generation`, `sql_repair`), is fully
testable with `httpx.MockTransport` standing in for the one adapter both
of them share.

---

## ADR 7 — No global state, no singleton services

See [ADR 2](#adr-2--constructor-dependency-injection-everywhere-no-globals-no-singletons)
— this is the same decision, restated as its own explicit rule because
every phase's specification called it out independently. Enforced
consistently: no pipeline package defines a module-level mutable instance
of any engine, registry, or cache.

---

## ADR 8 — Repair is a separate phase from validation

**Context.** *Detecting* that SQL is invalid and *fixing* it are different
problems requiring different tools — validation is a pure, local AST
inspection; repair requires another LLM round trip and a bounded retry
strategy.

**Decision.** `sql_repair.SQLRepairEngine` is its own package, invoked by
the orchestrator only when `SQLValidationResult.is_valid` is `False`, and
it re-validates its own output through the *same* `SQLValidationEngine`
(via `RepairValidator`) rather than re-implementing any validation logic.

**Consequences.** Validation stays simple, side-effect-free, and callable
as often as needed (see ADR 4). Repair owns everything specific to
*fixing* SQL — a bounded attempt loop (`RepairStrategy`,
`DEFAULT_MAX_ATTEMPTS`), a repair-specific prompt
(`RepairPromptBuilder`), and a full, never-overwritten attempt history
(`RepairHistory`) — without any of that complexity leaking into
validation.

---

## ADR 9 — Execution is a separate phase from formatting

**Context.** Running SQL against a real database (an I/O operation with
real cost and real failure modes — timeouts, connection errors, database
rejections) and turning rows into a presentable answer (a pure,
CPU-bound transformation) are different kinds of work with different
failure semantics.

**Decision.** `sql_execution.SQLExecutionEngine.execute` is the only
phase that touches the database, and it never raises for an ordinary
execution failure — every outcome becomes a structured
`SQLExecutionResult`. `result_formatter.ResultFormatterEngine.format`
accepts only a `SQLExecutionResult` whose `status` is already `SUCCESS`
and performs no database I/O at all.

**Consequences.** The orchestrator can inspect `SQLExecutionResult.status`
and short-circuit to a `FAILED` `QueryMindResponse` *before* ever calling
the formatter, rather than the formatter needing to handle (or reject) a
failed execution itself. It also means execution's read-only guarantees
(ADR 5, the AST guard plus the database-level read-only transaction) are
concentrated in exactly one place, never re-implemented or bypassed by a
formatting concern.

---

## Known gaps

Not formal ADRs, but worth recording precisely because each is a real,
currently-live inconsistency, discovered during development and left
as-is rather than silently patched — per this project's standing rule
that architectural findings get documented, not redesigned mid-phase.

### Gap 1: `SyntaxValidator` vs. `ExecutionGuard`

Discovered while implementing `sql_execution` (Phase 13):
`sql_validation.validators.syntax.SyntaxValidator` checks only
`isinstance(root, exp.Select)` on the result of `sqlglot.parse_one`, which
means it does not independently catch either of the two gaps described in
[ADR 5](#adr-5--sqlglot-as-the-sql-parser-never-regex) (multi-statement
smuggling, or a write hidden in a writable CTE).
`sql_execution.ExecutionGuard` closes both gaps for its own purposes, but
`SyntaxValidator` itself was left unchanged — Phase 13's instructions were
explicit that prior phases must not be redesigned mid-phase. If
`SyntaxValidator` is ever revisited, it should adopt the same
`sqlglot.parse` (not `parse_one`) plus full-AST-walk approach
`ExecutionGuard` already uses.

### Gap 2: `metadata.RelationshipGraph`'s three traversal methods are unreachable stubs

Discovered during the Phase 15.5 architecture audit. `RelationshipGraph
.find_related_tables`, `.shortest_path`, and `.find_join_path` are public
(exported in `metadata.__all__`), fully documented, and each
unconditionally raise `NotImplementedError("... is implemented in a later
phase.")`. No later phase ever implements or calls them: `schema_linker
.relationships.RelationshipPathResolver` and
`sql_validation.validators.joins.JoinValidator` each independently
implement their *own* breadth-first traversal directly on
`RelationshipGraph`'s low-level `edges_from`/`neighbors` accessors,
bypassing the three stub methods entirely. The result is public API
surface that always crashes if called, plus the same graph-traversal
algorithm implemented twice, once per consumer, instead of once in
`metadata` where the docstrings say it belongs. No test anywhere calls
any of the three stub methods. **Recommendation for a future change** (not
implemented here): either implement the three methods in
`RelationshipGraph` and have `schema_linker`/`sql_validation` adopt them,
or remove the stubs and their `__all__` export and update both
docstrings that still describe them as "reserved for a later phase."

### Gap 3: `sql_repair.prompt_builder` depends on non-exported `prompt_compiler` internals

Discovered during the Phase 15.5 public API audit.
`sql_repair.prompt_builder` imports `estimate_tokens` (from
`prompt_compiler.budget`), `CONSTRAINT_RULES` (from
`prompt_compiler.templates`), and `ConstraintSectionBuilder`/
`ExampleSectionBuilder`/`SystemSectionBuilder` (from
`prompt_compiler.sections`) — none of which appear in
`prompt_compiler.__all__`. This is a deliberate, functionally necessary
reuse (`RepairPromptBuilder` constructor-injects three repair-specific
section builders into the existing `PromptCompiler` machinery, reusing
its other four builders unchanged — see that module's own docstring), not
an accident, but it means `sql_repair` depends on `prompt_compiler`
internals that `prompt_compiler` has not declared as part of its public
contract: `prompt_compiler` could rename or relocate any of these five
names without knowing it breaks `sql_repair`. **Recommendation for a
future change** (not implemented here): add these five names to
`prompt_compiler.__all__`, making the existing dependency an honest,
declared one, rather than changing `sql_repair`'s reuse strategy.
