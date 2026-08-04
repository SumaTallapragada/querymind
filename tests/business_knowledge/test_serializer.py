from __future__ import annotations

import json

import yaml

from querymind.business_knowledge.models import BusinessKnowledgeCatalog
from querymind.business_knowledge.serializer import BusinessKnowledgeSerializer


def test_to_dict_produces_json_safe_primitives(sample_catalog: BusinessKnowledgeCatalog) -> None:
    concept = sample_catalog.concepts[0]
    result = BusinessKnowledgeSerializer.to_dict(concept)
    assert isinstance(result, dict)
    assert result["id"] == "revenue"
    assert isinstance(result["aliases"], list)
    assert result["aliases"][0] == {"text": "Turnover"}
    assert result["concept_type"] == "metric"


def test_to_json_round_trips_through_json_loads(sample_catalog: BusinessKnowledgeCatalog) -> None:
    concept = sample_catalog.concepts[0]
    text = BusinessKnowledgeSerializer.to_json(concept)
    parsed = json.loads(text)
    assert parsed["id"] == "revenue"
    assert parsed["name"] == "Revenue"


def test_to_yaml_round_trips_through_yaml_safe_load(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    concept = sample_catalog.concepts[0]
    text = BusinessKnowledgeSerializer.to_yaml(concept)
    parsed = yaml.safe_load(text)
    assert parsed["id"] == "revenue"
    assert parsed["aliases"] == [{"text": "Turnover"}]


def test_serializes_the_whole_catalog(sample_catalog: BusinessKnowledgeCatalog) -> None:
    result = BusinessKnowledgeSerializer.to_dict(sample_catalog)
    assert len(result["concepts"]) == len(sample_catalog.concepts)
    assert "loaded_at" in result
