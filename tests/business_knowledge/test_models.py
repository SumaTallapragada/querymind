from __future__ import annotations

import pytest

from querymind.business_knowledge.models import (
    BusinessConcept,
    BusinessConceptType,
    BusinessMetric,
)


def _concept(**overrides: object) -> BusinessConcept:
    defaults: dict[str, object] = {
        "id": "revenue",
        "name": "Revenue",
        "concept_type": BusinessConceptType.METRIC,
        "description": "Total amount charged to customers.",
        "calculation_description": "Sum of order totals.",
    }
    defaults.update(overrides)
    return BusinessConcept(**defaults)  # type: ignore[arg-type]


def test_aliases_accept_plain_strings_from_yaml() -> None:
    """`concepts.yaml` authors aliases as a plain string list, not `{text: ...}` objects."""
    concept = _concept(aliases=["Turnover", "Sales Revenue"])
    assert [alias.text for alias in concept.aliases] == ["Turnover", "Sales Revenue"]


def test_model_is_frozen() -> None:
    concept = _concept()
    with pytest.raises(Exception, match="frozen|immutable"):
        concept.name = "Something Else"  # type: ignore[misc]


def test_to_definition_projects_the_display_fields() -> None:
    concept = _concept(
        example_questions=("What is our revenue?",), aliases=["Turnover"], related_terms=["Sales"]
    )
    definition = concept.to_definition()
    assert definition.concept_id == "revenue"
    assert definition.name == "Revenue"
    assert definition.description == concept.description
    assert definition.calculation_description == concept.calculation_description
    assert definition.example_questions == ("What is our revenue?",)


def test_business_metric_from_concept() -> None:
    concept = _concept(concept_type=BusinessConceptType.METRIC)
    metric = BusinessMetric.from_concept(concept)
    assert metric.id == concept.id
    assert metric.concept_type is BusinessConceptType.METRIC


def test_business_metric_from_concept_rejects_non_metric_concepts() -> None:
    concept = _concept(concept_type=BusinessConceptType.SEGMENT)
    with pytest.raises(ValueError, match="METRIC"):
        BusinessMetric.from_concept(concept)
