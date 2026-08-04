"""The SQL Validation Engine: turns a `GeneratedSQL` into a `SQLValidationResult`.

`SQLValidationEngine` is the single public entry point for this package.
It parses the SQL once (via `SQLParser`), runs every validator in its
`ValidatorRegistry` against the resulting AST, and hands the combined
findings to `querymind.sql_validation.report.build_result`. The engine
itself never inspects SQL content — parsing is `SQLParser`'s job,
per-check logic is each `Validator`'s job, and assembling the final
result is `report.py`'s job. It never generates, modifies, repairs,
optimizes, or executes SQL, and never calls an LLM.

Per the architecture notes, one validator failing unexpectedly does not
stop the others from running — every validator call is individually
guarded, and a crash is reported as its own `ValidationIssue` rather than
aborting the whole run, so the caller still receives a complete picture.
"""

from __future__ import annotations

import time

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation import report
from querymind.sql_validation.exceptions import (
    BusinessRuleViolationError,
    SchemaValidationError,
    SQLSyntaxError,
)
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidatorExecutionTime,
)
from querymind.sql_validation.parser import (
    SQLParser,
    extract_columns,
    extract_functions,
    extract_joins,
    extract_tables,
)
from querymind.sql_validation.registry import ValidatorRegistry, build_default_registry

#: How `GeneratedSQL.dialect` maps onto a sqlglot dialect string.
_SQLGLOT_DIALECTS: dict[SQLDialect, str] = {
    SQLDialect.POSTGRESQL: "postgres",
    SQLDialect.MYSQL: "mysql",
    SQLDialect.SQLITE: "sqlite",
    SQLDialect.ANSI: "",
}


class SQLValidationEngine:
    """Validates a `GeneratedSQL` by running every validator in its `ValidatorRegistry`.

    Every collaborator — the parser, the validator registry — is
    constructor-injected with a sensible default, so a caller can supply
    a custom registry (a subset of validators, a different order, an
    extra one) without touching this class. `metadata_registry` and
    `business_knowledge_registry` are required directly only to build the
    default registry; a caller supplying their own `registry` doesn't
    need to pass them.
    """

    def __init__(
        self,
        metadata_registry: MetadataRegistry | None = None,
        business_knowledge_registry: BusinessKnowledgeRegistry | None = None,
        relationship_graph: RelationshipGraph | None = None,
        registry: ValidatorRegistry | None = None,
        parser: SQLParser | None = None,
    ) -> None:
        self._parser = parser or SQLParser()
        self._registry = registry or self._build_default_registry(
            metadata_registry, business_knowledge_registry, relationship_graph
        )

    @staticmethod
    def _build_default_registry(
        metadata_registry: MetadataRegistry | None,
        business_knowledge_registry: BusinessKnowledgeRegistry | None,
        relationship_graph: RelationshipGraph | None,
    ) -> ValidatorRegistry:
        if metadata_registry is None:
            raise SchemaValidationError(
                "metadata_registry is required to build the default ValidatorRegistry "
                "(or pass an explicit registry)."
            )
        if business_knowledge_registry is None:
            raise BusinessRuleViolationError(
                "business_knowledge_registry is required to build the default ValidatorRegistry "
                "(or pass an explicit registry)."
            )
        graph = relationship_graph or metadata_registry.build_graph()
        return build_default_registry(metadata_registry, business_knowledge_registry, graph)

    def validate(self, generated_sql: GeneratedSQL) -> SQLValidationResult:
        """Validate `generated_sql`. Always returns a result — never raises for an invalid query."""
        started = time.perf_counter()
        sqlglot_dialect = _SQLGLOT_DIALECTS.get(generated_sql.dialect, "postgres")

        try:
            parsed = self._parser.parse(generated_sql.sql, dialect=sqlglot_dialect)
        except SQLSyntaxError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return report.build_result(
                generated_sql=generated_sql,
                issues=(
                    ValidationIssue(
                        code="sql_syntax_error",
                        severity=ValidationSeverity.ERROR,
                        message=str(exc),
                    ),
                ),
                validated_tables=(),
                validated_columns=(),
                validated_functions=(),
                join_count=0,
                validator_execution_times=(),
                validation_latency_ms=latency_ms,
            )

        issues: list[ValidationIssue] = []
        execution_times: list[ValidatorExecutionTime] = []
        for validator in self._registry.validators:
            validator_started = time.perf_counter()
            try:
                issues.extend(validator.validate(parsed))
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        code="validator_internal_error",
                        severity=ValidationSeverity.ERROR,
                        message=f"Validator {validator.name!r} raised an unexpected error: {exc}",
                        related_object=validator.name,
                    )
                )
            execution_times.append(
                ValidatorExecutionTime(
                    validator=validator.name,
                    duration_ms=(time.perf_counter() - validator_started) * 1000,
                )
            )

        table_names = tuple(ref.name for ref in extract_tables(parsed.ast))
        column_names = tuple(
            f"{column.qualifier}.{column.name}" if column.qualifier else column.name
            for column in extract_columns(parsed.ast)
        )
        function_names = tuple(
            fn.name for fn in extract_functions(parsed.ast, dialect=sqlglot_dialect)
        )
        join_count = len(extract_joins(parsed.ast))

        latency_ms = (time.perf_counter() - started) * 1000
        return report.build_result(
            generated_sql=generated_sql,
            issues=issues,
            validated_tables=table_names,
            validated_columns=column_names,
            validated_functions=function_names,
            join_count=join_count,
            validator_execution_times=execution_times,
            validation_latency_ms=latency_ms,
        )
