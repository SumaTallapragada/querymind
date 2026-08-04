"""Tests for `querymind.sql_validation.validators.business_rules.BusinessRuleValidator`."""

from __future__ import annotations

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.models import ValidationSeverity
from querymind.sql_validation.validators.business_rules import BusinessRuleValidator
from tests.sql_validation.conftest import parse


def _validator(
    metadata_registry: MetadataRegistry, business_knowledge_registry: BusinessKnowledgeRegistry
) -> BusinessRuleValidator:
    return BusinessRuleValidator(business_knowledge_registry, metadata_registry)


class TestCorrectMetricUsage:
    def test_revenue_using_its_approved_column_produces_no_issue(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        sql = "SELECT SUM(o.total_amount) AS total_revenue FROM orders o;"
        issues = _validator(metadata_registry, business_knowledge_registry).validate(parse(sql))
        assert not any(issue.code == "business_metric_schema_mismatch" for issue in issues)

    def test_a_query_that_never_mentions_a_metric_by_name_is_not_checked_against_it(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        sql = "SELECT first_name FROM customers;"
        issues = _validator(metadata_registry, business_knowledge_registry).validate(parse(sql))
        assert issues == ()


class TestMismatchedMetricUsage:
    def test_a_query_naming_revenue_but_using_the_wrong_column_is_a_warning(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        sql = "SELECT SUM(o.discount_amount) AS total_revenue FROM orders o;"
        issues = _validator(metadata_registry, business_knowledge_registry).validate(parse(sql))
        mismatch = next(i for i in issues if i.code == "business_metric_schema_mismatch")
        assert mismatch.severity is ValidationSeverity.WARNING
        assert mismatch.related_object == "revenue"

    def test_an_alias_using_a_known_metric_alias_is_also_detected(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
    ) -> None:
        # "AOV" is a declared alias of Average Order Value.
        sql = "SELECT COUNT(*) AS aov FROM customers;"
        issues = _validator(metadata_registry, business_knowledge_registry).validate(parse(sql))
        assert any(issue.related_object == "average_order_value" for issue in issues)
