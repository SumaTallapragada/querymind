"""Prompt templates: section ordering, headers, and default inclusion.

A `PromptTemplate` is data, never behavior — it says which sections
appear, in what order, under what header. It never generates section
*content*; that is always `sections.py`'s job. Keeping this split is
what lets a future template (a more compact one, a differently ordered
one) be added without touching a single section builder.

Also the one place canonical, reusable prompt *text* (the system
preamble, the constraint rules, the output-format instructions) lives —
`sections.py`'s builders reference these constants rather than each
embedding its own copy of similar wording, so there is exactly one
place to edit the wording of an instruction.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from querymind.prompt_compiler.exceptions import PromptCompilationError
from querymind.prompt_compiler.models import SectionName


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


#: The system/role preamble every compiled prompt opens with.
SYSTEM_PREAMBLE = (
    "You are a precise, careful SQL-writing assistant for QueryMind, a text-to-SQL analytics "
    "engine. Given the business context, schema, relationships, and example queries below, "
    "write SQL that correctly answers the user's question. Use only the tables and columns "
    "explicitly listed — never invent a table or column name."
)

#: The fixed rules every compiled prompt's constraint section states.
CONSTRAINT_RULES: tuple[str, ...] = (
    "Only reference tables and columns explicitly listed in the Schema Context section.",
    "Never invent a table, column, or relationship that was not provided.",
    "Use the exact join paths given in the Relationships section when joining tables.",
    "Prefer the patterns shown in the Similar Examples section when one applies.",
    "Return exactly one SQL statement.",
    "Do not include any explanation, commentary, or markdown formatting around the SQL.",
)

#: Format string for the output section, parameterized by SQL dialect.
OUTPUT_FORMAT_INSTRUCTION = (
    "Write a single valid {dialect} SQL statement. Use clear indentation and standard SQL "
    "keywords in uppercase (SELECT, FROM, WHERE, GROUP BY, ...). Do not wrap the SQL in "
    "markdown code fences or add trailing commentary."
)


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
    itself. `DefaultPromptTemplate` is the standard implementation;
    "future extensibility" means a different `PromptTemplate` (different
    headers, a different order, a subset of sections) is just another
    instance of this same shape, not a change to this class.
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


#: The seven sections, in pipeline order, with their default headers —
#: what `DefaultPromptTemplate` is built from.
_DEFAULT_SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(name=SectionName.SYSTEM, header="# System Instructions", order=1),
    SectionSpec(name=SectionName.BUSINESS_CONTEXT, header="## Business Context", order=2),
    SectionSpec(name=SectionName.SCHEMA_CONTEXT, header="## Schema Context", order=3),
    SectionSpec(name=SectionName.RELATIONSHIP, header="## Table Relationships", order=4),
    SectionSpec(name=SectionName.RETRIEVED_EXAMPLES, header="## Similar Examples", order=5),
    SectionSpec(name=SectionName.CONSTRAINT, header="## Constraints", order=6),
    SectionSpec(name=SectionName.OUTPUT_FORMAT, header="## Output Format", order=7),
)


class DefaultPromptTemplate(PromptTemplate):
    """The standard QueryMind prompt template: all seven sections, in pipeline order."""

    version: str = "1.0.0"
    name: str = "default"
    section_specs: tuple[SectionSpec, ...] = _DEFAULT_SECTION_SPECS
