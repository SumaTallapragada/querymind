"""Tests for `querymind.sql_repair.engine.SQLRepairEngine` — repair loop orchestration."""

from __future__ import annotations

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.sql_repair.engine import SQLRepairEngine
from querymind.sql_repair.llm_adapter import SQLRepairLLMAdapter
from querymind.sql_repair.models import RepairReason, RepairStatus
from querymind.sql_repair.strategy import RepairStrategy
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation.engine import SQLValidationEngine

from .conftest import make_generated_sql, make_llm_adapter, make_llm_response

# A JOIN between two tables with no relationship in the real schema -- guaranteed invalid.
_BROKEN_SQL = (
    "SELECT c.customer_id, w.warehouse_id "
    "FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
)

# A correct query using a real relationship (customers/orders) -- guaranteed valid.
_FIXED_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
)


def _repair_validator(
    metadata_registry: MetadataRegistry, business_knowledge_registry: BusinessKnowledgeRegistry
) -> RepairValidator:
    return RepairValidator(SQLValidationEngine(metadata_registry, business_knowledge_registry))


class TestRepairSuccess:
    def test_a_single_successful_attempt_stops_the_loop(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )
        assert validation.is_valid is False

        llm_adapter = make_llm_adapter([make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```")])
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.status is RepairStatus.REPAIRED
        assert result.statistics.attempt_count == 1
        assert result.final_validation_result.is_valid is True
        assert result.final_sql.sql == _FIXED_SQL

    def test_original_sql_is_never_mutated(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )
        llm_adapter = make_llm_adapter([make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```")])
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.original_sql is generated
        assert result.original_sql.sql == _BROKEN_SQL

    def test_records_the_repair_reason_on_the_attempt(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )
        llm_adapter = make_llm_adapter([make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```")])
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.history.attempts[0].repair_reason is RepairReason.INVALID_JOIN
        assert result.history.attempts[0].success is True


class TestRepairEventualSuccess:
    def test_a_failed_attempt_followed_by_a_successful_one(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )

        still_broken = "SELECT c.customer_id, s.supplier_id FROM customers c JOIN suppliers s ON s.supplier_id = c.customer_id;"
        llm_adapter = make_llm_adapter(
            [
                make_llm_response(content=f"```sql\n{still_broken}\n```"),
                make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```"),
            ]
        )
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.status is RepairStatus.REPAIRED
        assert result.statistics.attempt_count == 2
        assert result.history.attempts[0].success is False
        assert result.history.attempts[1].success is True


class TestRepairFailure:
    def test_max_attempts_reached_when_errors_keep_changing(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )

        # Each variant fails with a genuinely different error *code* (unknown_join_relationship,
        # then missing_group_by, then unsupported_function), so RepairStrategy sees progress on
        # every attempt and the loop runs all the way to max_attempts rather than stopping early
        # on a no-progress detection.
        broken_variants = [
            "SELECT c.customer_id, w.warehouse_id FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;",
            "SELECT customer_id, SUM(total_amount) FROM orders;",
            "SELECT MY_BOGUS_FUNC(customer_id) FROM customers;",
        ]
        llm_adapter = make_llm_adapter(
            [make_llm_response(content=f"```sql\n{sql}\n```") for sql in broken_variants]
        )
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
            strategy=RepairStrategy(3),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.status is RepairStatus.MAX_ATTEMPTS_REACHED
        assert result.statistics.attempt_count == 3
        assert result.final_validation_result.is_valid is False

    def test_no_progress_stops_before_max_attempts(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )

        llm_adapter = make_llm_adapter(
            [make_llm_response(content=f"```sql\n{_BROKEN_SQL}\n```") for _ in range(3)]
        )
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
            strategy=RepairStrategy(3),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.status is RepairStatus.NO_PROGRESS
        assert result.statistics.attempt_count == 2

    def test_statistics_are_populated_correctly(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )
        llm_adapter = make_llm_adapter([make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```")])
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )

        result = engine.repair(generated, validation, bundle)
        assert result.statistics.attempt_count == 1
        assert result.statistics.successful_repairs == 1
        assert result.statistics.failed_repairs == 0
        assert result.statistics.repair_latency_ms >= 0.0
        assert result.statistics.average_validation_latency_ms >= 0.0


class TestDependencyInjection:
    def test_default_collaborators_are_used_when_none_given(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        bundle: RetrievedKnowledgeBundle,
    ) -> None:
        generated = make_generated_sql(_BROKEN_SQL)
        validation = _repair_validator(metadata_registry, business_knowledge_registry).validate(
            generated
        )
        llm_adapter = make_llm_adapter([make_llm_response(content=f"```sql\n{_FIXED_SQL}\n```")])
        engine = SQLRepairEngine(
            SQLRepairLLMAdapter(llm_adapter),
            _repair_validator(metadata_registry, business_knowledge_registry),
        )
        result = engine.repair(generated, validation, bundle)
        assert result.status is RepairStatus.REPAIRED
