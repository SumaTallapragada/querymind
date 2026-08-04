"""Loads the business concept data source from disk.

Pure I/O + per-entry validation: reads a YAML file and returns validated
`BusinessConcept` objects. Knows nothing about `BusinessKnowledgeCatalog`
duplicate-id checking or timestamps — that assembly logic lives in
`querymind.business_knowledge.catalog`, which consumes what this module
loads. Mirrors `querymind.metadata.loader` exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from querymind.business_knowledge.exceptions import CatalogLoadError
from querymind.business_knowledge.models import BusinessConcept

#: The concepts data file shipped with this package.
DEFAULT_CATALOG_PATH = Path(__file__).parent / "data" / "concepts.yaml"


def load_concepts_file(path: Path) -> tuple[BusinessConcept, ...]:
    """Read and validate a concepts YAML file into `BusinessConcept` objects, in file order.

    Raises `CatalogLoadError` if the file is missing, isn't valid YAML,
    or its content doesn't match `BusinessConcept`'s schema. Does not
    check for duplicate ids across entries — that cross-entry validation
    belongs to `querymind.business_knowledge.catalog.build_catalog`,
    which assembles this function's output into a
    `BusinessKnowledgeCatalog`.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogLoadError(str(path), f"could not read file: {exc}") from exc

    try:
        raw: Any = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise CatalogLoadError(str(path), f"invalid YAML: {exc}") from exc

    entries = raw.get("concepts")
    if entries is None:
        raise CatalogLoadError(str(path), "missing top-level 'concepts' key")

    try:
        return tuple(BusinessConcept(**entry) for entry in entries)
    except ValidationError as exc:
        raise CatalogLoadError(str(path), f"schema validation failed: {exc}") from exc
