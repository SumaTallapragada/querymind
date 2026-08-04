"""Checks table references are well-formed: known, uniquely aliased, and unambiguous.

Independent of `SchemaValidator` by construction — both consult the
Metadata Engine for "does this table exist," deliberately, so either can
be enabled/disabled without losing that check entirely. This validator's
distinct value is everything about *how* tables are referenced within
the query itself: duplicate aliases, and the same table named twice with
no alias to tell the references apart.
"""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL, extract_tables, local_scope_names


class TableValidator:
    """Validates unknown tables, duplicate table aliases, and unaliased duplicate table references."""

    name = "table"

    def __init__(self, metadata_registry: MetadataRegistry) -> None:
        self._metadata_registry = metadata_registry

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        local_names = local_scope_names(parsed.ast)
        known_tables = set(self._metadata_registry.list_tables())
        refs = extract_tables(parsed.ast)

        for ref in refs:
            if ref.name not in local_names and ref.name not in known_tables:
                issues.append(
                    ValidationIssue(
                        code="unknown_table",
                        severity=ValidationSeverity.ERROR,
                        message=f"Table {ref.name!r} does not exist in the schema.",
                        related_object=ref.name,
                    )
                )

        alias_counts: dict[str, int] = {}
        for ref in refs:
            if ref.alias:
                alias_counts[ref.alias] = alias_counts.get(ref.alias, 0) + 1
        for alias, count in alias_counts.items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        code="duplicate_table_alias",
                        severity=ValidationSeverity.ERROR,
                        message=f"Alias {alias!r} is declared {count} times.",
                        related_object=alias,
                    )
                )

        unaliased_names = [ref.name for ref in refs if not ref.alias]
        for name in set(unaliased_names):
            if unaliased_names.count(name) > 1:
                issues.append(
                    ValidationIssue(
                        code="ambiguous_table_reference",
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Table {name!r} is referenced more than once with no alias "
                            "to disambiguate the references."
                        ),
                        related_object=name,
                    )
                )

        return tuple(issues)
