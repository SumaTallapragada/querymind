"""Immutable data models for the Prompt Compiler.

`CompiledPrompt` is the single output type of
`querymind.prompt_compiler.compiler.PromptCompiler.compile` — a
`querymind.retrieval.RetrievedKnowledgeBundle` rendered into the seven
prompt sections an LLM-facing caller needs, plus compilation statistics.
Nothing here calls an LLM, generates SQL, or knows anything about a
specific model provider — see the package docstring for that boundary.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from querymind.prompt_compiler.exceptions import PromptCompilationError
from querymind.query_library.models import SQLDialect


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SectionName(str, Enum):
    """The seven prompt sections, matching the compilation pipeline's content-producing steps."""

    SYSTEM = "system"
    BUSINESS_CONTEXT = "business_context"
    SCHEMA_CONTEXT = "schema_context"
    RELATIONSHIP = "relationship"
    RETRIEVED_EXAMPLES = "retrieved_examples"
    CONSTRAINT = "constraint"
    OUTPUT_FORMAT = "output_format"


class SectionSpec(_FrozenModel):
    """One section's configuration within a `PromptTemplate`: its header, order, and default inclusion."""

    name: SectionName
    header: str = Field(
        description="The heading rendered above this section's content, e.g. '## Schema Context'."
    )
    order: int = Field(ge=1, description="Position in the assembled prompt — lower renders first.")
    include_by_default: bool = Field(
        default=True,
        description="Whether a compiler should build this section unless told otherwise.",
    )


class PromptTemplate(_FrozenModel):
    """Defines section ordering, headers, and default inclusion for prompt assembly.

    Data only — the actual section *content* is always produced by the
    dedicated builders in `sections.py`; a template never generates text
    itself. `DefaultPromptTemplate` (in `querymind.prompt_compiler.templates`)
    is the standard implementation; "future extensibility" means a
    different `PromptTemplate` (different headers, a different order, a
    subset of sections) is just another instance of this same shape, not
    a change to this class.

    Defined here, not in `templates.py`, so that `CompiledPrompt` below
    can store the exact `PromptTemplate` instance used to compile it —
    `templates.py` already imports `SectionName` from this module, and a
    reverse import (this module needing `templates.py`) would be
    circular. `templates.py` imports `PromptTemplate`/`SectionSpec` back
    from here to define `DefaultPromptTemplate`.
    """

    version: str
    name: str
    section_specs: tuple[SectionSpec, ...]

    def spec_for(self, name: SectionName) -> SectionSpec:
        """Return the `SectionSpec` for `name`. Raises `PromptCompilationError` if not in this template."""
        for spec in self.section_specs:
            if spec.name is name:
                return spec
        raise PromptCompilationError(
            f"Template {self.name!r} (v{self.version}) has no spec for {name.value!r}."
        )

    def ordered_names(self) -> tuple[SectionName, ...]:
        """Every section name in this template, sorted by `SectionSpec.order`."""
        return tuple(spec.name for spec in sorted(self.section_specs, key=lambda spec: spec.order))


#: Trim order for the three trimmable sections (`is_required=False`),
#: ascending — lower trims first. Relationship is grouped with schema
#: (trimmed together): join-path text is meaningless once the schema
#: listing it depends on has been cut, so there is no reason to trim
#: them independently, and the requested trim order only names three
#: tiers, not four. System/Constraint/Output never appear here — they
#: are `is_required=True` and the budget manager never considers them.
SCHEMA_TRIM_PRIORITY = 2
EXAMPLES_TRIM_PRIORITY = 1
BUSINESS_TRIM_PRIORITY = 3
#: Sentinel for sections the budget manager never trims regardless of
#: their `priority` value — `is_required=True` is what actually protects
#: them; this is just a readable placeholder for those sections' priority.
NOT_TRIMMABLE_PRIORITY = 0


class PromptSection(_FrozenModel):
    """One section of a `CompiledPrompt` — the base shape every specific section subclasses.

    `priority` only matters for sections where `is_required` is `False`:
    it is the trim order `querymind.prompt_compiler.budget.PromptBudgetManager`
    uses when the prompt is over budget (lower trims first). Required
    sections are never trimmed regardless of their `priority` value.
    """

    name: SectionName
    content: str = Field(description="The rendered text for this section.")
    estimated_tokens: int = Field(ge=0, description="Approximate token count of `content`.")
    priority: int = Field(
        ge=0, description="Trim order among non-required sections (lower trims first)."
    )
    is_required: bool = Field(
        description="Whether the budget manager must never trim this section."
    )


class SystemSection(PromptSection):
    """The system/role instructions — always required, never trimmed."""

    name: Literal[SectionName.SYSTEM] = SectionName.SYSTEM
    priority: int = NOT_TRIMMABLE_PRIORITY
    is_required: Literal[True] = True


class BusinessSection(PromptSection):
    """The business terminology relevant to the question — trimmed last among trimmable sections."""

    name: Literal[SectionName.BUSINESS_CONTEXT] = SectionName.BUSINESS_CONTEXT
    priority: int = BUSINESS_TRIM_PRIORITY
    is_required: Literal[False] = False


class SchemaSection(PromptSection):
    """The resolved tables/columns relevant to the question — trimmed second among trimmable sections.

    `schema_objects` is additional structured data beyond the base
    `PromptSection` shape, for the same reason `ExampleSection.example_ids`
    exists: statistics/validation need to count *actual* schema objects,
    not approximate that by parsing rendered prose.
    """

    name: Literal[SectionName.SCHEMA_CONTEXT] = SectionName.SCHEMA_CONTEXT
    priority: int = SCHEMA_TRIM_PRIORITY
    is_required: Literal[False] = False
    schema_objects: tuple[str, ...] = Field(
        default=(),
        description="The 'table'/'table.column' identifiers actually rendered into `content`.",
    )


class RelationshipSection(PromptSection):
    """The join paths connecting the resolved tables — trimmed alongside `SchemaSection`."""

    name: Literal[SectionName.RELATIONSHIP] = SectionName.RELATIONSHIP
    priority: int = SCHEMA_TRIM_PRIORITY
    is_required: Literal[False] = False


class ExampleSection(PromptSection):
    """The retrieved gold examples — trimmed first among trimmable sections.

    `example_ids` is additional structured data beyond the base
    `PromptSection` shape: `querymind.prompt_compiler.validator.
    PromptValidator`'s "no duplicate examples" rule needs the underlying
    example identifiers, not just the rendered prose in `content`.
    """

    name: Literal[SectionName.RETRIEVED_EXAMPLES] = SectionName.RETRIEVED_EXAMPLES
    priority: int = EXAMPLES_TRIM_PRIORITY
    is_required: Literal[False] = False
    example_ids: tuple[str, ...] = Field(
        default=(), description="The QueryExample ids actually rendered into `content`, in order."
    )


class ConstraintSection(PromptSection):
    """The rules the generated SQL must follow — always required, never trimmed."""

    name: Literal[SectionName.CONSTRAINT] = SectionName.CONSTRAINT
    priority: int = NOT_TRIMMABLE_PRIORITY
    is_required: Literal[True] = True


class OutputSection(PromptSection):
    """The expected output format/dialect instructions — always required, never trimmed."""

    name: Literal[SectionName.OUTPUT_FORMAT] = SectionName.OUTPUT_FORMAT
    priority: int = NOT_TRIMMABLE_PRIORITY
    is_required: Literal[True] = True


class SectionTokenUsage(_FrozenModel):
    """How many tokens one section used in a compiled prompt."""

    section: SectionName
    estimated_tokens: int = Field(ge=0)


class PromptStatistics(_FrozenModel):
    """Observability data about one `PromptCompiler.compile` call."""

    estimated_total_tokens: int = Field(
        ge=0, description="Sum of every section's estimated_tokens."
    )
    section_token_usage: tuple[SectionTokenUsage, ...] = Field(default=())
    retrieved_example_count: int = Field(
        ge=0, description="How many gold examples made it into the final prompt."
    )
    schema_object_count: int = Field(
        ge=0, description="How many tables/columns made it into the final prompt."
    )
    compilation_latency_ms: float = Field(
        ge=0.0, description="Wall-clock time compilation took, in milliseconds."
    )


def _default_prompt_template() -> PromptTemplate:
    """The default value for `CompiledPrompt.template` when a caller doesn't supply one.

    A local import — not a mistake: `DefaultPromptTemplate` lives in
    `querymind.prompt_compiler.templates`, which imports `PromptTemplate`
    from *this* module, so a top-level import here would be circular.
    Deferred until this factory actually runs, by which point both
    modules are fully loaded.
    """
    from querymind.prompt_compiler.templates import DefaultPromptTemplate

    return DefaultPromptTemplate()


class CompiledPrompt(_FrozenModel):
    """The complete output of one compilation: all seven sections, plus statistics.

    Every field a caller needs is a direct attribute; call `as_text()`
    to render the whole thing into one prompt string via
    `querymind.prompt_compiler.formatter.PromptFormatter`, using the
    exact `template` this prompt was compiled with — never a silently
    substituted default.
    """

    system: SystemSection
    business_context: BusinessSection
    schema_context: SchemaSection
    relationships: RelationshipSection
    examples: ExampleSection
    constraints: ConstraintSection
    output_format: OutputSection
    statistics: PromptStatistics
    template: PromptTemplate = Field(
        default_factory=_default_prompt_template,
        description="The exact PromptTemplate instance used to assemble this prompt — "
        "`as_text()` renders with this, never a substituted default. `template_version` "
        "below is redundant with `template.version`, kept only for backward compatibility "
        "with callers that read the plain string.",
    )
    template_version: str = Field(
        description="The PromptTemplate.version used to assemble this prompt."
    )
    dialect: SQLDialect = Field(
        description="The SQL dialect the output_format section instructs toward."
    )

    def all_sections(self) -> tuple[PromptSection, ...]:
        """Every section, in pipeline order (`SYSTEM` first, `OUTPUT_FORMAT` last)."""
        return (
            self.system,
            self.business_context,
            self.schema_context,
            self.relationships,
            self.examples,
            self.constraints,
            self.output_format,
        )

    def as_text(self) -> str:
        """Render this prompt into one string, via `PromptFormatter`, using `self.template`.

        A local import — not a mistake: `PromptFormatter` needs
        `CompiledPrompt` for its own type signature, so a top-level
        import here would be circular. This is the standard, accepted
        way to resolve a model-needs-a-service-that-needs-the-model
        dependency in Python.
        """
        from querymind.prompt_compiler.formatter import PromptFormatter

        return PromptFormatter(self.template).format(self)
