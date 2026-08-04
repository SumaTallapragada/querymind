from __future__ import annotations

from pathlib import Path

import pytest

from querymind.business_knowledge.catalog import build_catalog, load_catalog
from querymind.business_knowledge.exceptions import DuplicateConceptError
from querymind.business_knowledge.models import BusinessConcept, BusinessConceptType


def _concept(concept_id: str, name: str) -> BusinessConcept:
    return BusinessConcept(
        id=concept_id,
        name=name,
        concept_type=BusinessConceptType.METRIC,
        description="x",
        calculation_description="x",
    )


def test_build_catalog_assembles_concepts_and_sets_loaded_at() -> None:
    catalog = build_catalog([_concept("revenue", "Revenue"), _concept("sales", "Sales")])
    assert [c.id for c in catalog.concepts] == ["revenue", "sales"]
    assert catalog.loaded_at is not None


def test_build_catalog_rejects_duplicate_ids() -> None:
    with pytest.raises(DuplicateConceptError, match="revenue"):
        build_catalog([_concept("revenue", "Revenue"), _concept("revenue", "Also Revenue")])


def test_load_catalog_reads_and_assembles_a_real_file(tmp_path: Path) -> None:
    path = tmp_path / "concepts.yaml"
    path.write_text(
        """
concepts:
  - id: revenue
    name: Revenue
    concept_type: metric
    description: "x"
    calculation_description: "x"
""",
        encoding="utf-8",
    )
    catalog = load_catalog(path)
    assert len(catalog.concepts) == 1
    assert catalog.concepts[0].id == "revenue"


def test_load_catalog_default_path_loads_the_shipped_catalog() -> None:
    catalog = load_catalog()
    assert len(catalog.concepts) > 0
