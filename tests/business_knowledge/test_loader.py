from __future__ import annotations

from pathlib import Path

import pytest

from querymind.business_knowledge.exceptions import CatalogLoadError
from querymind.business_knowledge.loader import load_concepts_file

_VALID_YAML = """
concepts:
  - id: revenue
    name: Revenue
    concept_type: metric
    description: "Total amount charged to customers."
    aliases: ["Turnover"]
    calculation_description: "Sum of order totals."
  - id: top_customer
    name: Top Customer
    concept_type: segment
    description: "A customer ranked highest by spend."
    calculation_description: "Ranked by total order value."
"""


def test_loads_valid_yaml_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "concepts.yaml"
    path.write_text(_VALID_YAML, encoding="utf-8")
    concepts = load_concepts_file(path)
    assert [c.id for c in concepts] == ["revenue", "top_customer"]
    assert concepts[0].name == "Revenue"
    assert [a.text for a in concepts[0].aliases] == ["Turnover"]


def test_missing_file_raises_catalog_load_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogLoadError, match="could not read file"):
        load_concepts_file(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_catalog_load_error(tmp_path: Path) -> None:
    path = tmp_path / "concepts.yaml"
    path.write_text("concepts: [this is not: valid: yaml: at all", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="invalid YAML"):
        load_concepts_file(path)


def test_missing_concepts_key_raises_catalog_load_error(tmp_path: Path) -> None:
    path = tmp_path / "concepts.yaml"
    path.write_text("not_concepts: []", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="missing top-level 'concepts' key"):
        load_concepts_file(path)


def test_schema_validation_failure_raises_catalog_load_error(tmp_path: Path) -> None:
    path = tmp_path / "concepts.yaml"
    path.write_text(
        """
concepts:
  - id: revenue
    name: Revenue
    concept_type: not_a_real_type
    description: "x"
    calculation_description: "x"
""",
        encoding="utf-8",
    )
    with pytest.raises(CatalogLoadError, match="schema validation failed"):
        load_concepts_file(path)


def test_default_catalog_path_exists() -> None:
    from querymind.business_knowledge.loader import DEFAULT_CATALOG_PATH

    assert DEFAULT_CATALOG_PATH.exists()
