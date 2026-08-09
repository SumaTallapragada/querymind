"""Exports auth Pydantic models (e.g. `UserRead`, `TokenPair`) to JSON, YAML, or a plain dict.

Mirrors `querymind.sql_execution.serializer.SQLExecutionSerializer`/
`querymind.prompt_compiler.serializer.PromptCompilerSerializer`-style exporters used throughout
this project exactly. Never given a `User` ORM instance directly -- callers convert to
`UserRead` first (see `querymind.auth.schemas`), the same "Pydantic only" boundary every other
package's serializer already enforces by its type signature.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel


class AuthenticationSerializer:
    """Stateless exporter for any `querymind.auth` Pydantic model -- a plain namespace of static
    methods rather than an instance you configure, matching every other phase's serializer.
    """

    @staticmethod
    def to_dict(model: BaseModel) -> dict[str, Any]:
        """Return `model` as a plain, JSON-safe dict (datetimes become ISO strings, ...)."""
        return model.model_dump(mode="json")

    @staticmethod
    def to_json(model: BaseModel, *, indent: int | None = 2) -> str:
        """Return `model` as a JSON string."""
        return model.model_dump_json(indent=indent)

    @staticmethod
    def to_yaml(model: BaseModel) -> str:
        """Return `model` as a YAML string.

        Goes through `to_dict` first so PyYAML only ever sees JSON-safe primitives
        (str/int/float/bool/list/dict) -- never a Pydantic-specific type it would need special
        handling for.
        """
        return yaml.safe_dump(
            AuthenticationSerializer.to_dict(model), sort_keys=False, allow_unicode=True
        )
