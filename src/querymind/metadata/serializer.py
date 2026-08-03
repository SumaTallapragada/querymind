"""Exports metadata models to JSON, YAML, or a plain dict.

This is the boundary every future consumer — Prompt Builder, Admin UI,
evaluation harness, documentation generator — is expected to read
through. They receive a dict/JSON/YAML string produced here, never a
live Pydantic object and never a SQLAlchemy model.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel


class MetadataSerializer:
    """Stateless exporter for any metadata Pydantic model (e.g. `DatabaseMetadata`).

    A plain namespace of static methods rather than an instance you
    configure — serialization has no state of its own, so there is
    nothing to inject or hold onto between calls.
    """

    @staticmethod
    def to_dict(metadata: BaseModel) -> dict[str, Any]:
        """Return `metadata` as a plain, JSON-safe dict (tuples become lists, etc.)."""
        return metadata.model_dump(mode="json")

    @staticmethod
    def to_json(metadata: BaseModel, *, indent: int | None = 2) -> str:
        """Return `metadata` as a JSON string."""
        return metadata.model_dump_json(indent=indent)

    @staticmethod
    def to_yaml(metadata: BaseModel) -> str:
        """Return `metadata` as a YAML string.

        Goes through `to_dict` first so PyYAML only ever sees JSON-safe
        primitives (str/int/float/bool/list/dict) — never a `datetime`,
        `tuple`, or Pydantic-specific type it would need special
        handling for.
        """
        return yaml.safe_dump(
            MetadataSerializer.to_dict(metadata), sort_keys=False, allow_unicode=True
        )
