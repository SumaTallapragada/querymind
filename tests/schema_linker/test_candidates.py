from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.schema_linker.candidates import CandidateGenerator
from querymind.schema_linker.models import MatchTier


def test_table_candidates_are_ranked_best_first(sample_registry: MetadataRegistry) -> None:
    generator = CandidateGenerator(sample_registry)
    candidates = generator.generate_table_candidates("customer")
    assert candidates[0].table_name == "customers"
    assert candidates[0].matching_reason is MatchTier.EXACT
    assert [c.candidate_rank for c in candidates] == list(range(1, len(candidates) + 1))
    confidences = [c.confidence for c in candidates]
    assert confidences == sorted(confidences, reverse=True)


def test_column_candidates_found_across_every_table(sample_registry: MetadataRegistry) -> None:
    generator = CandidateGenerator(sample_registry)
    candidates = generator.generate_column_candidates("revenue")
    assert len(candidates) == 1
    assert candidates[0].table_name == "orders"
    assert candidates[0].column_name == "total_amount"
    assert candidates[0].matching_reason is MatchTier.SYNONYM


def test_multiple_columns_matching_produces_multiple_candidates(
    sample_registry: MetadataRegistry,
) -> None:
    """Two columns sharing the synonym "location" must both appear — nothing discarded."""
    generator = CandidateGenerator(sample_registry)
    candidates = generator.generate_column_candidates("location")
    assert len(candidates) == 2
    matched_columns = {(c.table_name, c.column_name) for c in candidates}
    assert matched_columns == {("customers", "region"), ("orders", "ship_region")}


def test_no_match_returns_an_empty_tuple(sample_registry: MetadataRegistry) -> None:
    generator = CandidateGenerator(sample_registry)
    assert generator.generate_table_candidates("nonexistent_concept_xyz") == ()
    assert generator.generate_column_candidates("nonexistent_concept_xyz") == ()


def test_results_are_cached_across_calls(sample_registry: MetadataRegistry) -> None:
    generator = CandidateGenerator(sample_registry)
    first = generator.generate_column_candidates("revenue")
    second = generator.generate_column_candidates("revenue")
    assert first is second


def test_table_and_column_lookups_for_the_same_concept_are_cached_separately(
    sample_registry: MetadataRegistry,
) -> None:
    generator = CandidateGenerator(sample_registry)
    table_candidates = generator.generate_table_candidates("customer")
    column_candidates = generator.generate_column_candidates("customer")
    assert all(c.column_name is None for c in table_candidates)
    assert all(c.column_name is not None for c in column_candidates)
