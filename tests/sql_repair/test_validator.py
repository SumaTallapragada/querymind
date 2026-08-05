"""Tests for `querymind.sql_repair.validator.RepairValidator`."""

from __future__ import annotations

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation.engine import SQLValidationEngine

from .conftest import make_generated_sql


class TestValidate:
    def test_delegates_to_the_underlying_validation_engine(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        validator = RepairValidator(validation_engine)

        generated = make_generated_sql("SELECT customer_id FROM customers;")
        result = validator.validate(generated)
        assert result.is_valid is True
        assert result.generated_sql == generated

    def test_reports_the_same_errors_the_underlying_engine_would(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        validation_engine = SQLValidationEngine(metadata_registry, business_knowledge_registry)
        validator = RepairValidator(validation_engine)

        generated = make_generated_sql("SELECT * FROM nonexistent_table;")
        direct_result = validation_engine.validate(generated)
        wrapped_result = validator.validate(generated)
        assert wrapped_result.errors == direct_result.errors
