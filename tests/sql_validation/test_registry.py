"""Tests for `querymind.sql_validation.registry`."""

from __future__ import annotations

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.sql_validation.registry import ValidatorRegistry, build_default_registry
from querymind.sql_validation.validators.schema import SchemaValidator
from querymind.sql_validation.validators.syntax import SyntaxValidator


class TestValidatorRegistry:
    def test_holds_validators_in_the_given_order(self) -> None:
        registry = ValidatorRegistry([SyntaxValidator(), SyntaxValidator()])
        assert len(registry.validators) == 2

    def test_validators_is_immutable(self) -> None:
        registry = ValidatorRegistry([SyntaxValidator()])
        assert isinstance(registry.validators, tuple)

    def test_an_empty_registry_is_valid(self) -> None:
        registry = ValidatorRegistry([])
        assert registry.validators == ()


class TestBuildDefaultRegistry:
    def test_builds_all_ten_validators(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        relationship_graph: RelationshipGraph,
    ) -> None:
        registry = build_default_registry(
            metadata_registry, business_knowledge_registry, relationship_graph
        )
        assert len(registry.validators) == 10

    def test_starts_with_syntax_and_ends_with_dialect(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        relationship_graph: RelationshipGraph,
    ) -> None:
        registry = build_default_registry(
            metadata_registry, business_knowledge_registry, relationship_graph
        )
        names = [validator.name for validator in registry.validators]
        assert names[0] == "syntax"
        assert names[-1] == "dialect"

    def test_follows_the_architecture_specified_order(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        relationship_graph: RelationshipGraph,
    ) -> None:
        registry = build_default_registry(
            metadata_registry, business_knowledge_registry, relationship_graph
        )
        names = [validator.name for validator in registry.validators]
        assert names == [
            "syntax",
            "schema",
            "table",
            "column",
            "join",
            "function",
            "aggregate",
            "alias",
            "business_rule",
            "dialect",
        ]

    def test_schema_validator_is_wired_to_the_given_metadata_registry(
        self,
        metadata_registry: MetadataRegistry,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        relationship_graph: RelationshipGraph,
    ) -> None:
        registry = build_default_registry(
            metadata_registry, business_knowledge_registry, relationship_graph
        )
        schema_validator = next(v for v in registry.validators if isinstance(v, SchemaValidator))
        assert schema_validator._metadata_registry is metadata_registry
