"""Exports repair models to JSON, YAML, or a plain dict.

Mirrors `querymind.prompt_compiler.serializer.PromptCompilerSerializer` /
`querymind.query_library.serializer.QueryLibrarySerializer`-style
exporters used throughout this project exactly.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel


class SQLRepairSerializer:
    """Stateless exporter for any sql_repair Pydantic model (e.g. `SQLRepairResult`).

    A plain namespace of static methods rather than an instance you
    configure — serialization has no state of its own to hold between
    calls.
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
        primitives (str/int/float/bool/list/dict) — never a Pydantic-
        specific type it would need special handling for.
        """
        return yaml.safe_dump(
            SQLRepairSerializer.to_dict(model), sort_keys=False, allow_unicode=True
        )
