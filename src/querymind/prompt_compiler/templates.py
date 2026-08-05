"""Prompt templates: section ordering, headers, and default inclusion.

A `PromptTemplate` is data, never behavior — it says which sections
appear, in what order, under what header. It never generates section
*content*; that is always `sections.py`'s job. Keeping this split is
what lets a future template (a more compact one, a differently ordered
one) be added without touching a single section builder.

`PromptTemplate`/`SectionSpec` themselves are defined in `models.py`,
not here — `CompiledPrompt` (also in `models.py`) stores the exact
`PromptTemplate` instance it was compiled with, and this module already
imports `SectionName` from `models.py`, so defining `PromptTemplate`
here too would make that a circular import. This module owns the
*default* template (`DefaultPromptTemplate`) and the canonical, reusable
prompt *text* (the system preamble, the constraint rules, the
output-format instructions) — `sections.py`'s builders reference these
constants rather than each embedding its own copy of similar wording, so
there is exactly one place to edit the wording of an instruction.
"""

from __future__ import annotations

from querymind.prompt_compiler.models import PromptTemplate, SectionName, SectionSpec

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
