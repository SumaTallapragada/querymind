"""Checks column references are well-formed: known, unambiguous, and validly qualified.

Complements `SchemaValidator`'s "does this column exist" with the
distinct, scope-driven checks a column reference can fail even when the
underlying schema is perfectly fine: an unqualified name matching more
than one table in scope (ambiguous), or a qualifier that doesn't match
any declared table/alias at all (invalid qualification).
"""

from __future__ import annotations

from sqlglot import exp

from querymind.metadata.exceptions import TableNotFoundError
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import (
    ParsedSQL,
    build_alias_map,
    extract_columns,
    local_scope_names,
)


class ColumnValidator:
    """Validates unknown/ambiguous columns, invalid qualification, and nonexistent-column references."""

    name = "column"

    def __init__(self, metadata_registry: MetadataRegistry) -> None:
        self._metadata_registry = metadata_registry

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        alias_map = build_alias_map(parsed.ast)
        local_names = local_scope_names(parsed.ast)
        tables_in_scope = {table for table in alias_map.values() if table not in local_names}
        output_aliases = self._output_aliases(parsed.ast)

        for column in extract_columns(parsed.ast):
            if column.qualifier is not None:
                if column.qualifier not in alias_map:
                    issues.append(
                        ValidationIssue(
                            code="invalid_qualification",
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Column qualifier {column.qualifier!r} does not match any "
                                "table or alias in scope."
                            ),
                            related_object=f"{column.qualifier}.{column.name}",
                        )
                    )
                    continue
                real_table = alias_map[column.qualifier]
                if real_table in local_names:
                    continue  # a CTE/derived table's columns aren't checked against the Metadata Engine
                if not self._column_exists(real_table, column.name):
                    issues.append(
                        ValidationIssue(
                            code="unknown_column",
                            severity=ValidationSeverity.ERROR,
                            message=f"Column {column.name!r} does not exist on table {real_table!r}.",
                            related_object=f"{real_table}.{column.name}",
                        )
                    )
                continue

            if column.name in output_aliases:
                continue  # a reference to this query's own SELECT-list alias, not a schema column

            owners = [table for table in tables_in_scope if self._column_exists(table, column.name)]
            if not owners:
                issues.append(
                    ValidationIssue(
                        code="unknown_column",
                        severity=ValidationSeverity.ERROR,
                        message=f"Column {column.name!r} does not exist on any table in scope.",
                        related_object=column.name,
                    )
                )
            elif len(owners) > 1:
                issues.append(
                    ValidationIssue(
                        code="ambiguous_column",
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Column {column.name!r} exists on more than one table in scope "
                            f"({', '.join(sorted(owners))}) and must be qualified."
                        ),
                        related_object=column.name,
                    )
                )

        return tuple(issues)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        try:
            table = self._metadata_registry.get_table(table_name)
        except TableNotFoundError:
            return False
        return any(column.name == column_name for column in table.columns)

    @staticmethod
    def _output_aliases(ast: exp.Expression) -> frozenset[str]:
        if not isinstance(ast, exp.Select):
            return frozenset()
        return frozenset(
            item.alias for item in ast.expressions if isinstance(item, exp.Alias) and item.alias
        )
