"""Checks business metrics reference their approved schema objects.

Sourced from `querymind.business_knowledge.BusinessKnowledgeRegistry`
(for the metric catalog — Revenue, Return Rate, Average Order Value,
Customer Lifetime Value, ...) and `querymind.metadata.MetadataRegistry`
indirectly (through the tables/columns the SQL itself references). Never
modifies the SQL.

This validator's input is only the generated SQL text and AST — it has
no access to the original natural-language question or the resolved
business concepts the NLU Engine/Schema Linker found for it (that
context lives upstream, in `querymind.nlu`/`querymind.schema_linker`, and
does not flow into `GeneratedSQL`). It can therefore only apply a
best-effort, text-level heuristic for "is this query computing metric
X": whether the metric's name or one of its aliases appears in the SQL
text (most often via a `SELECT ... AS total_revenue`-style output
alias). This is reported as a WARNING, not an ERROR — a heuristic
mismatch is a hint worth surfacing, not proof the SQL is wrong.
"""

from __future__ import annotations

from sqlglot import exp

from querymind.business_knowledge.models import BusinessMetric
from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import (
    ParsedSQL,
    build_alias_map,
    extract_columns,
    extract_tables,
)


class BusinessRuleValidator:
    """Validates that a business metric a query appears to compute uses its approved schema objects."""

    name = "business_rule"

    def __init__(
        self,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        metadata_registry: MetadataRegistry,
    ) -> None:
        self._business_knowledge_registry = business_knowledge_registry
        self._metadata_registry = metadata_registry

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        referenced_objects = self._referenced_schema_objects(parsed.ast)
        raw_lower = parsed.raw_sql.lower()

        for metric in self._business_knowledge_registry.list_metrics():
            if not metric.preferred_schema_objects:
                continue
            if not self._metric_is_mentioned(metric, raw_lower):
                continue
            if any(obj in referenced_objects for obj in metric.preferred_schema_objects):
                continue
            issues.append(
                ValidationIssue(
                    code="business_metric_schema_mismatch",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Query appears to compute {metric.name!r} but references none of its "
                        f"approved schema objects ({', '.join(metric.preferred_schema_objects)})."
                    ),
                    related_object=metric.id,
                )
            )

        return tuple(issues)

    @staticmethod
    def _metric_is_mentioned(metric: BusinessMetric, raw_sql_lower: str) -> bool:
        names = (metric.name, *(alias.text for alias in metric.aliases))
        return any(name.lower() in raw_sql_lower for name in names)

    @staticmethod
    def _referenced_schema_objects(ast: exp.Expression) -> frozenset[str]:
        alias_map = build_alias_map(ast)
        objects: set[str] = {ref.name for ref in extract_tables(ast)}
        for column in extract_columns(ast):
            table = alias_map.get(column.qualifier) if column.qualifier else None
            if table:
                objects.add(f"{table}.{column.name}")
        return frozenset(objects)
