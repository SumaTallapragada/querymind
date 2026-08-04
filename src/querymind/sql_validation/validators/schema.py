"""Checks referenced tables, columns, and schemas exist, per the Metadata Engine.

The authoritative "does this real thing exist" check — sourced entirely
from `querymind.metadata.MetadataRegistry`, the single existing source of
truth for the database's structure. Never modifies the SQL or the
registry; only reads.
"""

from __future__ import annotations

from querymind.metadata.exceptions import TableNotFoundError
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import (
    ParsedSQL,
    build_alias_map,
    extract_columns,
    extract_tables,
    local_scope_names,
)

#: The only schema this single-database project's tables live in.
_SUPPORTED_SCHEMA = "public"


class SchemaValidator:
    """Validates referenced tables/columns/schemas exist in the Metadata Engine."""

    name = "schema"

    def __init__(self, metadata_registry: MetadataRegistry) -> None:
        self._metadata_registry = metadata_registry

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        local_names = local_scope_names(parsed.ast)
        known_tables = set(self._metadata_registry.list_tables())

        for ref in extract_tables(parsed.ast):
            if ref.name in local_names:
                continue
            schema_node = ref.node.args.get("db")
            if schema_node is not None:
                schema_name = getattr(schema_node, "name", str(schema_node))
                if schema_name.lower() != _SUPPORTED_SCHEMA:
                    issues.append(
                        ValidationIssue(
                            code="unknown_schema",
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Schema {schema_name!r} is not supported "
                                f"(only {_SUPPORTED_SCHEMA!r} is)."
                            ),
                            related_object=ref.name,
                        )
                    )
            if ref.name not in known_tables:
                issues.append(
                    ValidationIssue(
                        code="unknown_table",
                        severity=ValidationSeverity.ERROR,
                        message=f"Table {ref.name!r} does not exist in the schema.",
                        related_object=ref.name,
                    )
                )

        alias_map = build_alias_map(parsed.ast)
        for column in extract_columns(parsed.ast):
            if column.qualifier is None or column.qualifier in local_names:
                continue
            real_table = alias_map.get(column.qualifier)
            if real_table is None or real_table not in known_tables:
                continue  # unresolvable/unknown table already reported above
            if not self._column_exists(real_table, column.name):
                issues.append(
                    ValidationIssue(
                        code="unknown_column",
                        severity=ValidationSeverity.ERROR,
                        message=f"Column {column.name!r} does not exist on table {real_table!r}.",
                        related_object=f"{real_table}.{column.name}",
                    )
                )

        return tuple(issues)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        try:
            table = self._metadata_registry.get_table(table_name)
        except TableNotFoundError:
            return False
        return any(column.name == column_name for column in table.columns)
