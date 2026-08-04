"""Exports query library models to JSON, YAML, or a plain dict.

This is the boundary any future consumer (a Retrieval Engine, an admin
UI, a documentation generator) is expected to read through — a
dict/JSON/YAML string produced here, never a live Pydantic object.
Mirrors `querymind.metadata.serializer.MetadataSerializer` /
`querymind.business_knowledge.serializer.BusinessKnowledgeSerializer`
exactly.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel


class QueryLibrarySerializer:
    """Stateless exporter for any query library Pydantic model (e.g. `QueryExample`).

    A plain namespace of static methods rather than an instance you
    configure — serialization has no state of its own, so there is
    nothing to inject or hold onto between calls.
    """

    @staticmethod
    def to_dict(model: BaseModel) -> dict[str, Any]:
        """Return `model` as a plain, JSON-safe dict (tuples become lists, enums become their value, ...)."""
        return model.model_dump(mode="json")

    @staticmethod
    def to_json(model: BaseModel, *, indent: int | None = 2) -> str:
        """Return `model` as a JSON string."""
        return model.model_dump_json(indent=indent)

    @staticmethod
    def to_yaml(model: BaseModel) -> str:
        """Return `model` as a YAML string.

        Goes through `to_dict` first so PyYAML only ever sees JSON-safe
        primitives (str/int/float/bool/list/dict) — never a `datetime`
        or Pydantic-specific type it would need special handling for.
        """
        return yaml.safe_dump(
            QueryLibrarySerializer.to_dict(model), sort_keys=False, allow_unicode=True
        )
