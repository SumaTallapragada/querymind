"""Candidate generation: scan the whole loaded schema for every match a concept has.

`CandidateGenerator` is what turns "does concept X match this one
column?" (`querymind.schema_linker.matcher.ConceptMatcher`) into "every
table/column in the schema concept X matches, ranked" — the full
candidate list `querymind.schema_linker.resolver.ConceptResolver` and
`querymind.schema_linker.ambiguity.AmbiguityDetector` need to decide
whether a concept resolves confidently. Never stops at the first match:
per the linking strategy's ambiguity requirement, every table/column that
matches at any tier becomes its own candidate — nothing is discarded
here.
"""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.schema_linker.cache import InMemoryLinkerCache, LinkerCache
from querymind.schema_linker.matcher import ConceptMatcher, normalize_concept
from querymind.schema_linker.models import LinkCandidate, MatchTier
from querymind.schema_linker.scorer import ConfidenceScorer


class CandidateGenerator:
    """Generates every ranked `LinkCandidate` for a business concept, across the whole schema.

    Table candidates are matched against each table's `name`/`synonyms`
    (tables carry no `search_keywords`/`display_name` in the Metadata
    Engine's model); column candidates are matched against each column's
    `name`/`synonyms`/`search_keywords`/`display_name`. Full table and
    column *descriptions* are deliberately excluded from matching —
    they're prose, not vocabulary, and would turn fuzzy/partial matching
    into noise.
    """

    def __init__(
        self,
        registry: MetadataRegistry,
        matcher: ConceptMatcher | None = None,
        scorer: ConfidenceScorer | None = None,
        cache: LinkerCache | None = None,
    ) -> None:
        self._registry = registry
        self._matcher = matcher or ConceptMatcher()
        self._scorer = scorer or ConfidenceScorer()
        self._cache = cache or InMemoryLinkerCache()

    def generate_table_candidates(self, concept: str) -> tuple[LinkCandidate, ...]:
        """Every table the schema has that `concept` matches at any tier, ranked best first."""
        key = (True, normalize_concept(concept))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        candidates: list[LinkCandidate] = []
        for table in self._registry.load().tables:
            result = self._matcher.match(concept, name=table.name, synonyms=table.synonyms)
            if result is not None:
                candidates.append(
                    LinkCandidate(
                        table_name=table.name,
                        column_name=None,
                        confidence=self._scorer.score(result),
                        matching_reason=result.tier,
                        candidate_rank=1,  # placeholder; corrected by _rank below
                        matched_text=result.matched_text,
                    )
                )

        ranked = _rank(candidates)
        self._cache.set(key, ranked)
        return ranked

    def generate_column_candidates(self, concept: str) -> tuple[LinkCandidate, ...]:
        """Every column the schema has that `concept` matches at any tier, ranked best first."""
        key = (False, normalize_concept(concept))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        candidates: list[LinkCandidate] = []
        for table in self._registry.load().tables:
            for column in table.columns:
                result = self._matcher.match(
                    concept,
                    name=column.name,
                    synonyms=column.synonyms,
                    search_keywords=column.search_keywords,
                    display_name=column.display_name,
                )
                if result is not None:
                    candidates.append(
                        LinkCandidate(
                            table_name=table.name,
                            column_name=column.name,
                            confidence=self._scorer.score(result),
                            matching_reason=result.tier,
                            candidate_rank=1,  # placeholder; corrected by _rank below
                            matched_text=result.matched_text,
                        )
                    )

        ranked = _rank(candidates)
        self._cache.set(key, ranked)
        return ranked


#: Tier priority for tie-breaking candidates of equal confidence — lower
#: is better. Derived from `MatchTier`'s declaration order so the two
#: never drift apart.
_TIER_PRIORITY: dict[MatchTier, int] = {tier: index for index, tier in enumerate(MatchTier)}


def _rank(candidates: list[LinkCandidate]) -> tuple[LinkCandidate, ...]:
    """Sort `candidates` by confidence (desc), tier priority (asc) as a tiebreak, then assign rank."""
    ordered = sorted(
        candidates,
        key=lambda candidate: (-candidate.confidence, _TIER_PRIORITY[candidate.matching_reason]),
    )
    return tuple(
        candidate.model_copy(update={"candidate_rank": rank})
        for rank, candidate in enumerate(ordered, start=1)
    )
