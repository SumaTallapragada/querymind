"""Loads the query example data source from disk.

Pure I/O + per-entry validation: reads a YAML file and returns validated
`QueryExample` objects. Knows nothing about `QueryExampleLibrary`
duplicate-id checking or timestamps — that assembly logic lives in
`querymind.query_library.catalog`, which consumes what this module
loads. Mirrors `querymind.metadata.loader` /
`querymind.business_knowledge.loader` exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from querymind.query_library.exceptions import LibraryLoadError
from querymind.query_library.models import QueryExample

#: The examples data file shipped with this package.
DEFAULT_LIBRARY_PATH = Path(__file__).parent / "data" / "examples.yaml"


def load_examples_file(path: Path) -> tuple[QueryExample, ...]:
    """Read and validate an examples YAML file into `QueryExample` objects, in file order.

    Raises `LibraryLoadError` if the file is missing, isn't valid YAML,
    or its content doesn't match `QueryExample`'s schema. Does not check
    for duplicate ids across entries — that cross-entry validation
    belongs to `querymind.query_library.catalog.build_library`, which
    assembles this function's output into a `QueryExampleLibrary`.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LibraryLoadError(str(path), f"could not read file: {exc}") from exc

    try:
        raw: Any = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise LibraryLoadError(str(path), f"invalid YAML: {exc}") from exc

    entries = raw.get("examples")
    if entries is None:
        raise LibraryLoadError(str(path), "missing top-level 'examples' key")

    try:
        return tuple(QueryExample(**entry) for entry in entries)
    except ValidationError as exc:
        raise LibraryLoadError(str(path), f"schema validation failed: {exc}") from exc
