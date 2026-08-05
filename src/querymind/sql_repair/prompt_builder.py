"""Builds repair prompts by reusing the existing Prompt Compiler — never a second one.

`PromptCompiler` already has everything a repair prompt needs (section
ordering, headers, token budgeting, validation, statistics) — it just
needs different section *content* for three of its seven slots. Every
one of its seven section builders is constructor-injectable, so
`RepairPromptBuilder` supplies three repair-specific builders (system,
"examples", constraints) and leaves the other four
(business/schema/relationships/output) exactly as `PromptCompiler`
already builds them for a first-pass compile. `RepairPromptTemplate`
supplies repair-appropriate headers for the same seven section slots —
`querymind.prompt_compiler.templates.PromptTemplate` is explicitly
designed to be subclassed this way (see its own docstring: "a different
`PromptTemplate` ... is just another instance of this same shape").

Nothing in `querymind.prompt_compiler` is modified to make this work.

The `ExampleSection` slot is repurposed: for a first-pass compile it
holds retrieved gold examples, but for a repair prompt the far more
useful content is the specific SQL that failed and exactly why —
`RepairPromptTemplate` gives this slot the header `"## SQL Requiring
Repair"` to make that repurposing honest rather than misleading.
"""

from __future__ import annotations

from querymind.prompt_compiler.budget import estimate_tokens
from querymind.prompt_compiler.compiler import PromptCompiler
from querymind.prompt_compiler.models import (
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    PromptTemplate,
    SectionName,
    SectionSpec,
    SystemSection,
)
from querymind.prompt_compiler.sections import (
    ConstraintSectionBuilder,
    ExampleSectionBuilder,
    SystemSectionBuilder,
)
from querymind.prompt_compiler.templates import CONSTRAINT_RULES
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_repair.planner import RepairPlan
from querymind.sql_validation.models import SQLValidationResult

#: The repair-specific system preamble. Fixed, reusable text -- never built inline
#: inside a builder, matching `querymind.prompt_compiler.templates`'s own convention.
REPAIR_SYSTEM_PREAMBLE = (
    "You are a precise SQL repair assistant for QueryMind. You will be given a "
    "previously generated SQL query that failed validation, the exact validation "
    "errors it produced, and the schema and relationships it must draw from. Your "
    "job is to fix ONLY the reported errors."
)

#: Repair-only rules, appended after the standard constraint rules every compiled
#: prompt already states.
REPAIR_RULES: tuple[str, ...] = (
    "Repair ONLY the reported validation errors -- do not rewrite unrelated parts of the query.",
    "Do not change the intended business question the query answers.",
    "Do not invent a table that was not already provided.",
    "Do not invent a column that was not already provided.",
    "Do not invent a relationship that was not already provided.",
    "Preserve the original query's intent.",
    "Return exactly one repaired SQL statement, and nothing else.",
)


class RepairSystemSectionBuilder(SystemSectionBuilder):
    """Builds the repair-specific system preamble. Ignores `bundle` and `dialect`."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> SystemSection:
        return SystemSection(
            content=REPAIR_SYSTEM_PREAMBLE, estimated_tokens=estimate_tokens(REPAIR_SYSTEM_PREAMBLE)
        )


class RepairContextSectionBuilder(ExampleSectionBuilder):
    """Builds the section showing the SQL to repair, its validation errors, and the repair plan.

    Constructor-injected with this attempt's `GeneratedSQL`/
    `SQLValidationResult`/`RepairPlan` — the `SectionBuilder` protocol's
    `build(bundle, dialect)` signature has no room for them, so they are
    bound once per repair attempt when `RepairPromptBuilder` constructs
    a fresh instance of this class (see the module docstring on why a
    fresh `PromptCompiler` is built per attempt).
    """

    def __init__(
        self, generated_sql: GeneratedSQL, validation_result: SQLValidationResult, plan: RepairPlan
    ) -> None:
        self._generated_sql = generated_sql
        self._validation_result = validation_result
        self._plan = plan

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> ExampleSection:
        error_lines = [
            f"- [{issue.code}] {issue.message}" for issue in self._validation_result.errors
        ]
        content = (
            f"SQL requiring repair:\n{self._generated_sql.sql}\n\n"
            f"{self._plan.summary}\n\n"
            "Validation errors:\n" + "\n".join(error_lines)
        )
        return ExampleSection(content=content, estimated_tokens=estimate_tokens(content))


class RepairConstraintSectionBuilder(ConstraintSectionBuilder):
    """Builds the standard constraint rules plus explicit repair-only rules."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> ConstraintSection:
        lines = [f"- {rule}" for rule in (*CONSTRAINT_RULES, *REPAIR_RULES)]
        content = "\n".join(lines)
        return ConstraintSection(content=content, estimated_tokens=estimate_tokens(content))


#: The repair template: the same seven section slots as `DefaultPromptTemplate`,
#: with headers reflecting repair semantics for the two repurposed slots.
_REPAIR_SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(name=SectionName.SYSTEM, header="# System Instructions", order=1),
    SectionSpec(name=SectionName.BUSINESS_CONTEXT, header="## Business Context", order=2),
    SectionSpec(name=SectionName.SCHEMA_CONTEXT, header="## Schema Context", order=3),
    SectionSpec(name=SectionName.RELATIONSHIP, header="## Table Relationships", order=4),
    SectionSpec(name=SectionName.RETRIEVED_EXAMPLES, header="## SQL Requiring Repair", order=5),
    SectionSpec(name=SectionName.CONSTRAINT, header="## Repair Rules", order=6),
    SectionSpec(name=SectionName.OUTPUT_FORMAT, header="## Output Format", order=7),
)


class RepairPromptTemplate(PromptTemplate):
    """The repair prompt template — same shape as `DefaultPromptTemplate`, repair-flavored headers."""

    version: str = "1.0.0-repair"
    name: str = "repair"
    section_specs: tuple[SectionSpec, ...] = _REPAIR_SECTION_SPECS


class RepairPromptBuilder:
    """Builds a repair `CompiledPrompt`, reusing `PromptCompiler`'s full pipeline."""

    def __init__(self, template: PromptTemplate | None = None) -> None:
        self._template = template or RepairPromptTemplate()

    def build(
        self,
        bundle: RetrievedKnowledgeBundle,
        generated_sql: GeneratedSQL,
        validation_result: SQLValidationResult,
        plan: RepairPlan,
    ) -> CompiledPrompt:
        """Compile a repair prompt for `generated_sql`, given its `validation_result` and `plan`.

        Constructs a fresh `PromptCompiler` per call — its default
        `InMemoryPromptCache` starts empty each time, which matters:
        `PromptCompiler`'s own cache key is `(bundle hash, template
        version, dialect)` and knows nothing about the repair-specific
        content baked into the builders below, so sharing a compiler (or
        its cache) across repair attempts would risk a stale hit for a
        genuinely different validation_result.
        """
        compiler = PromptCompiler(
            template=self._template,
            system_builder=RepairSystemSectionBuilder(),
            example_builder=RepairContextSectionBuilder(generated_sql, validation_result, plan),
            constraint_builder=RepairConstraintSectionBuilder(),
        )
        return compiler.compile(bundle, dialect=generated_sql.dialect)
