"""Loads the business dictionary data source from disk.

Pure I/O + validation: reads a YAML file and returns validated
`TableDictionaryEntry`/`ColumnDictionaryEntry` objects. Knows nothing
about `DatabaseMetadata` or how the dictionary gets merged into it — that
composition logic lives in `querymind.metadata.dictionary.ColumnDictionary`,
which consumes what this module loads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from querymind.metadata.exceptions import DictionaryLoadError
from querymind.metadata.models import ColumnDictionaryEntry, TableDictionaryEntry

#: The dictionary data file shipped with this package, transcribed from
#: the approved Phase 2 design doc (docs/phase2_database_design.md §5).
DEFAULT_DICTIONARY_PATH = Path(__file__).parent / "data" / "dictionary.yaml"


def load_dictionary_file(
    path: Path,
) -> tuple[dict[str, TableDictionaryEntry], dict[tuple[str, str], ColumnDictionaryEntry]]:
    """Read and validate a dictionary YAML file.

    Returns two lookup-ready mappings: table name -> `TableDictionaryEntry`,
    and `(table name, column name)` -> `ColumnDictionaryEntry`. Raises
    `DictionaryLoadError` if the file is missing, isn't valid YAML, or its
    content doesn't match the expected shape.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DictionaryLoadError(str(path), f"could not read file: {exc}") from exc

    try:
        raw: Any = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise DictionaryLoadError(str(path), f"invalid YAML: {exc}") from exc

    try:
        tables = {
            table_name: TableDictionaryEntry(table=table_name, **entry)
            for table_name, entry in (raw.get("tables") or {}).items()
        }
        columns: dict[tuple[str, str], ColumnDictionaryEntry] = {}
        for qualified_name, entry in (raw.get("columns") or {}).items():
            table_name, _, column_name = qualified_name.partition(".")
            if not column_name:
                raise DictionaryLoadError(
                    str(path), f"column key {qualified_name!r} is not in 'table.column' form"
                )
            columns[(table_name, column_name)] = ColumnDictionaryEntry(
                table=table_name, column=column_name, **entry
            )
    except ValidationError as exc:
        raise DictionaryLoadError(str(path), f"schema validation failed: {exc}") from exc

    return tables, columns
