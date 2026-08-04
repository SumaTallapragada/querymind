"""Holds the ordered set of validators `SQLValidationEngine` runs.

The extensibility point the architecture asks for: a validator can be
enabled, disabled, reordered, or replaced by constructing a different
`ValidatorRegistry` — never by editing another validator or the engine
itself. `build_default_registry` wires up the standard ten-validator
pipeline, in the architecture's specified order, from the three existing
QueryMind collaborators every validator that needs one is injected with.
"""

from __future__ import annotations

from collections.abc import Sequence

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.metadata.registry import MetadataRegistry
from querymind.metadata.relationships import RelationshipGraph
from querymind.sql_validation.validators import (
    AggregateValidator,
    AliasValidator,
    BusinessRuleValidator,
    ColumnValidator,
    DialectValidator,
    FunctionValidator,
    JoinValidator,
    SchemaValidator,
    SyntaxValidator,
    TableValidator,
    Validator,
)


class ValidatorRegistry:
    """An ordered, immutable collection of `Validator`s."""

    def __init__(self, validators: Sequence[Validator]) -> None:
        self._validators = tuple(validators)

    @property
    def validators(self) -> tuple[Validator, ...]:
        return self._validators


def build_default_registry(
    metadata_registry: MetadataRegistry,
    business_knowledge_registry: BusinessKnowledgeRegistry,
    relationship_graph: RelationshipGraph,
    *,
    dialect: str = "postgres",
) -> ValidatorRegistry:
    """Build the standard pipeline: Syntax, Schema, Table, Column, Join, Function, Aggregate, Alias, BusinessRule, Dialect."""
    return ValidatorRegistry(
        [
            SyntaxValidator(),
            SchemaValidator(metadata_registry),
            TableValidator(metadata_registry),
            ColumnValidator(metadata_registry),
            JoinValidator(relationship_graph),
            FunctionValidator(),
            AggregateValidator(),
            AliasValidator(),
            BusinessRuleValidator(business_knowledge_registry, metadata_registry),
            DialectValidator(dialect=dialect),
        ]
    )
