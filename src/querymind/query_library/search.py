"""Deterministic, keyword-based search over a loaded query example library.

No embeddings, no vector search — every method here is a normalized
string equality or substring/containment check, the same deterministic
philosophy as `querymind.business_knowledge.resolver` and
`querymind.schema_linker.matcher`. This is a lookup utility over
*already-loaded* examples, not a retrieval engine: ranking, relevance
scoring, and combining multiple search signals are explicitly a later
phase's job.
"""

from __future__ import annotations

from collections.abc import Sequence

from querymind.query_library.models import Difficulty, QueryExample


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace, so search is case/spacing-insensitive."""
    return " ".join(text.strip().lower().split())


class QueryExampleSearch:
    """Deterministic search over one loaded set of `QueryExample`s.

    Built from a plain sequence of examples (not a live registry), so it
    stays a small, pure, easily-testable unit — `QueryLibraryRegistry`
    is what constructs a fresh one from whatever's currently loaded.
    """

    def __init__(self, examples: Sequence[QueryExample]) -> None:
        self._examples = tuple(examples)

    def by_title(self, text: str) -> tuple[QueryExample, ...]:
        """Every example whose `title` contains `text` (case-insensitive substring match)."""
        normalized_text = _normalize(text)
        return tuple(
            example for example in self._examples if normalized_text in _normalize(example.title)
        )

    def by_tag(self, tag: str) -> tuple[QueryExample, ...]:
        """Every example whose `tags` contains `tag` exactly (case-insensitive)."""
        normalized_tag = _normalize(tag)
        return tuple(
            example
            for example in self._examples
            if any(_normalize(candidate) == normalized_tag for candidate in example.tags)
        )

    def by_business_concept(self, concept: str) -> tuple[QueryExample, ...]:
        """Every example whose `business_concepts` contains `concept` exactly (case-insensitive)."""
        normalized_concept = _normalize(concept)
        return tuple(
            example
            for example in self._examples
            if any(
                _normalize(candidate) == normalized_concept
                for candidate in example.business_concepts
            )
        )

    def by_difficulty(self, difficulty: Difficulty) -> tuple[QueryExample, ...]:
        """Every example at exactly `difficulty`."""
        return tuple(example for example in self._examples if example.difficulty is difficulty)

    def by_keywords(self, keywords: Sequence[str]) -> tuple[QueryExample, ...]:
        """Every example whose question contains *every* keyword (case-insensitive, order-independent).

        Checked against `natural_language_question`, `normalized_question`,
        and `title` together, so a keyword matching any of the three counts.
        """
        normalized_keywords = [_normalize(keyword) for keyword in keywords if keyword.strip()]
        if not normalized_keywords:
            return ()
        return tuple(
            example
            for example in self._examples
            if self._matches_all_keywords(example, normalized_keywords)
        )

    @staticmethod
    def _matches_all_keywords(example: QueryExample, normalized_keywords: Sequence[str]) -> bool:
        haystack = " ".join(
            (
                _normalize(example.title),
                _normalize(example.natural_language_question),
                _normalize(example.normalized_question),
            )
        )
        return all(keyword in haystack for keyword in normalized_keywords)
