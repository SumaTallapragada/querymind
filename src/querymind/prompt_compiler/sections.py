"""The seven dedicated section builders.

Each builder has exactly one responsibility — building its own section —
and knows nothing about any other builder, or about the template that
will decide this section's header/order/inclusion (that is
`compiler.py` and `templates.py`'s concern, not this module's). Every
builder implements the same `SectionBuilder` protocol so `compiler.py`
can treat them uniformly; the *content* each one produces is entirely
its own concern, sourced from the parts of a `RetrievedKnowledgeBundle`
(and the `querymind.query_library`/`querymind.schema_linker`/
`querymind.metadata` objects it already embeds) relevant to that one
section.
"""

from __future__ import annotations

from typing import Protocol

from querymind.prompt_compiler.budget import estimate_tokens
from querymind.prompt_compiler.models import (
    BusinessSection,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptSection,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.prompt_compiler.templates import (
    CONSTRAINT_RULES,
    OUTPUT_FORMAT_INSTRUCTION,
    SYSTEM_PREAMBLE,
)
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.schema_linker.models import LinkedQueryContext

_NO_BUSINESS_CONCEPTS = "No specific business concepts were identified for this question."
_NO_SCHEMA_OBJECTS = "No schema objects were resolved for this question."
_NO_RELATIONSHIPS = "No table joins are required to answer this question."
_NO_EXAMPLES = "No similar example questions were found in the query library."


class SectionBuilder(Protocol):
    """Builds one `PromptSection` from a `RetrievedKnowledgeBundle`."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> PromptSection:
        """Build this builder's section. `dialect` is only used by builders that need it."""
        ...


class SystemSectionBuilder:
    """Builds the fixed system/role preamble. Ignores `bundle` and `dialect` entirely."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> SystemSection:
        return SystemSection(
            content=SYSTEM_PREAMBLE, estimated_tokens=estimate_tokens(SYSTEM_PREAMBLE)
        )


class BusinessSectionBuilder:
    """Builds a listing of the business concepts relevant to the question.

    Sourced from `LinkedQueryContext.query_context.business_concepts`
    (the full set the NLU Engine found, whether or not the Schema Linker
    went on to resolve it) — the most complete available view of what
    the question is *about*, in business terms.
    """

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> BusinessSection:
        concepts = bundle.linked_query_context.query_context.business_concepts
        if not concepts:
            content = _NO_BUSINESS_CONCEPTS
        else:
            lines = [f"- {concept}" for concept in concepts]
            content = "This question relates to the following business concepts:\n" + "\n".join(
                lines
            )
        return BusinessSection(content=content, estimated_tokens=estimate_tokens(content))


class SchemaSectionBuilder:
    """Builds a listing of every resolved table/column, with its business meaning where known.

    Sourced entirely from the real `TableMetadata`/`ColumnMetadata`
    objects the `LinkedQueryContext` already carries (originally produced
    by the Metadata Engine, via the Schema Linker) — this builder never
    queries a registry itself and never imports `querymind.models`.
    """

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> SchemaSection:
        context = bundle.linked_query_context
        table_identifiers, table_lines = self._tables(context)
        column_identifiers, column_lines = self._columns(context)
        lines = [*table_lines, *column_lines]
        content = _NO_SCHEMA_OBJECTS if not lines else "\n".join(lines)
        return SchemaSection(
            content=content,
            estimated_tokens=estimate_tokens(content),
            schema_objects=(*table_identifiers, *column_identifiers),
        )

    @staticmethod
    def _tables(context: LinkedQueryContext) -> tuple[tuple[str, ...], list[str]]:
        tables = []
        if context.primary_entity is not None:
            tables.append(context.primary_entity.table)
        tables.extend(entity.table for entity in context.secondary_entities)
        identifiers: list[str] = []
        lines: list[str] = []
        seen: set[str] = set()
        for table in tables:
            if table.name in seen:
                continue
            seen.add(table.name)
            identifiers.append(table.name)
            description = f" — {table.description}" if table.description else ""
            lines.append(f"Table `{table.name}`{description}")
        return tuple(identifiers), lines

    @staticmethod
    def _columns(context: LinkedQueryContext) -> tuple[tuple[str, ...], list[str]]:
        columns = [metric.column for metric in context.metrics]
        columns.extend(dimension.column for dimension in context.dimensions)
        columns.extend(filter_.column for filter_ in context.filters)
        if context.sort is not None:
            columns.append(context.sort.column)
        identifiers: list[str] = []
        lines: list[str] = []
        seen: set[str] = set()
        for column in columns:
            key = f"{column.table_name}.{column.name}"
            if key in seen:
                continue
            seen.add(key)
            identifiers.append(key)
            description = f" — {column.description}" if column.description else ""
            lines.append(f"Column `{key}` ({column.sql_type}){description}")
        return tuple(identifiers), lines


class RelationshipSectionBuilder:
    """Builds a listing of the join paths connecting the resolved tables."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> RelationshipSection:
        paths = bundle.linked_query_context.relationship_paths
        if not paths:
            content = _NO_RELATIONSHIPS
        else:
            lines = [
                f"`{edge.source_table}.{'/'.join(edge.source_columns)}` -> "
                f"`{edge.target_table}.{'/'.join(edge.target_columns)}` (via `{edge.relationship_name}`)"
                for edge in paths
            ]
            content = "Join these tables as follows:\n" + "\n".join(lines)
        return RelationshipSection(content=content, estimated_tokens=estimate_tokens(content))


class ExampleSectionBuilder:
    """Builds a listing of the retrieved gold examples: question, SQL, and explanation for each."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> ExampleSection:
        if not bundle.retrieved_examples:
            return ExampleSection(
                content=_NO_EXAMPLES, estimated_tokens=estimate_tokens(_NO_EXAMPLES), example_ids=()
            )

        blocks = []
        example_ids: list[str] = []
        for index, retrieved in enumerate(bundle.retrieved_examples, start=1):
            example = retrieved.example
            example_ids.append(example.id)
            blocks.append(
                f"Example {index}: {example.title}\n"
                f"Question: {example.natural_language_question}\n"
                f"SQL:\n{example.gold_sql.strip()}\n"
                f"Explanation: {example.sql_explanation}"
            )
        content = "\n\n".join(blocks)
        return ExampleSection(
            content=content,
            estimated_tokens=estimate_tokens(content),
            example_ids=tuple(example_ids),
        )


class ConstraintSectionBuilder:
    """Builds the fixed list of rules the generated SQL must follow. Ignores `bundle` and `dialect`."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> ConstraintSection:
        content = "\n".join(f"- {rule}" for rule in CONSTRAINT_RULES)
        return ConstraintSection(content=content, estimated_tokens=estimate_tokens(content))


class OutputSectionBuilder:
    """Builds the output-format instructions, parameterized by the target SQL `dialect`."""

    def build(self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect) -> OutputSection:
        content = OUTPUT_FORMAT_INSTRUCTION.format(dialect=dialect.value)
        return OutputSection(content=content, estimated_tokens=estimate_tokens(content))
