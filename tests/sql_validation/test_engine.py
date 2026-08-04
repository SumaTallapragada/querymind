"""Tests for `querymind.sql_validation.engine.SQLValidationEngine` — validator orchestration."""

from __future__ import annotations

import pytest

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.engine import SQLValidationEngine
from querymind.sql_validation.exceptions import BusinessRuleViolationError, SchemaValidationError
from querymind.sql_validation.models import ValidationIssue
from querymind.sql_validation.parser import ParsedSQL
from querymind.sql_validation.registry import ValidatorRegistry

from .conftest import make_generated_sql


class TestValidateHappyPath:
    def test_a_correct_query_is_valid(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        sql = (
            "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
            "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
            "GROUP BY c.customer_id;"
        )
        result = engine.validate(make_generated_sql(sql))
        assert result.is_valid is True
        assert result.errors == ()

    def test_result_carries_the_input_generated_sql(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        generated = make_generated_sql("SELECT 1;")
        result = engine.validate(generated)
        assert result.generated_sql == generated

    def test_statistics_capture_every_validators_execution_time(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        result = engine.validate(make_generated_sql("SELECT customer_id FROM customers;"))
        assert len(result.validation_statistics.validator_execution_times) == 10

    def test_validated_tables_columns_functions_are_populated(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        sql = "SELECT c.customer_id, SUM(o.total_amount) FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id;"
        result = engine.validate(make_generated_sql(sql))
        assert "customers" in result.validated_tables
        assert "orders" in result.validated_tables
        assert "SUM" in result.validated_functions
        assert result.validation_statistics.join_count == 1


class TestValidateSyntaxFailure:
    def test_a_syntax_error_produces_a_single_critical_issue(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        result = engine.validate(make_generated_sql("SELECT FROM WHERE;"))
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "sql_syntax_error"

    def test_a_syntax_error_never_raises_out_of_validate(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        # Should not raise -- the caller always gets a complete result back.
        result = engine.validate(make_generated_sql("SELECT FROM WHERE;"))
        assert result is not None

    def test_a_syntax_error_produces_no_table_or_column_statistics(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        result = engine.validate(make_generated_sql("SELECT FROM WHERE;"))
        assert result.validated_tables == ()
        assert result.validation_statistics.validator_execution_times == ()


class TestValidatorCrashIsolation:
    def test_one_validator_raising_does_not_stop_the_others(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        class _CrashingValidator:
            name = "crasher"

            def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
                raise RuntimeError("boom")

        class _WellBehavedValidator:
            name = "well_behaved"
            called = False

            def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
                _WellBehavedValidator.called = True
                return ()

        registry = ValidatorRegistry([_CrashingValidator(), _WellBehavedValidator()])
        engine = SQLValidationEngine(registry=registry)
        result = engine.validate(make_generated_sql("SELECT 1;"))

        assert _WellBehavedValidator.called is True
        assert any(issue.code == "validator_internal_error" for issue in result.errors)
        assert result.is_valid is False

    def test_the_crash_issue_names_the_failing_validator(self) -> None:
        class _CrashingValidator:
            name = "my_validator"

            def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
                raise RuntimeError("boom")

        registry = ValidatorRegistry([_CrashingValidator()])
        engine = SQLValidationEngine(registry=registry)
        result = engine.validate(make_generated_sql("SELECT 1;"))
        assert result.errors[0].related_object == "my_validator"


class TestDependencyInjection:
    def test_requires_metadata_registry_when_no_explicit_registry_given(
        self, business_knowledge_registry: BusinessKnowledgeRegistry
    ) -> None:
        with pytest.raises(SchemaValidationError):
            SQLValidationEngine(business_knowledge_registry=business_knowledge_registry)

    def test_requires_business_knowledge_registry_when_no_explicit_registry_given(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        with pytest.raises(BusinessRuleViolationError):
            SQLValidationEngine(metadata_registry=metadata_registry)

    def test_an_explicit_registry_needs_neither_collaborator(self) -> None:
        engine = SQLValidationEngine(registry=ValidatorRegistry([]))
        result = engine.validate(make_generated_sql("SELECT 1;"))
        assert result.is_valid is True

    def test_an_empty_registry_produces_only_the_ast_derived_statistics(self) -> None:
        engine = SQLValidationEngine(registry=ValidatorRegistry([]))
        result = engine.validate(make_generated_sql("SELECT customer_id FROM customers;"))
        assert result.validated_tables == ("customers",)
        assert result.errors == ()
