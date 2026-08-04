from __future__ import annotations

import json

import yaml

from querymind.query_library.models import QueryExampleLibrary
from querymind.query_library.serializer import QueryLibrarySerializer


def test_to_dict_produces_json_safe_primitives(sample_library: QueryExampleLibrary) -> None:
    example = sample_library.examples[0]
    result = QueryLibrarySerializer.to_dict(example)
    assert isinstance(result, dict)
    assert result["id"] == "customer_count"
    assert result["difficulty"] == "beginner"
    assert isinstance(result["tags"], list)


def test_to_json_round_trips_through_json_loads(sample_library: QueryExampleLibrary) -> None:
    example = sample_library.examples[0]
    text = QueryLibrarySerializer.to_json(example)
    parsed = json.loads(text)
    assert parsed["id"] == "customer_count"
    assert parsed["title"] == "Total Customer Count"


def test_to_yaml_round_trips_through_yaml_safe_load(sample_library: QueryExampleLibrary) -> None:
    example = sample_library.examples[0]
    text = QueryLibrarySerializer.to_yaml(example)
    parsed = yaml.safe_load(text)
    assert parsed["id"] == "customer_count"
    assert parsed["query_context"]["intent"] == "count"


def test_serializes_the_whole_library(sample_library: QueryExampleLibrary) -> None:
    result = QueryLibrarySerializer.to_dict(sample_library)
    assert len(result["examples"]) == len(sample_library.examples)
    assert "loaded_at" in result
