"""Sorts scored candidates and truncates to the top-K, deterministically.

Ties in `overall_score` are broken by `QueryExample.id` (ascending) —
never by insertion order, which would make the result depend on
`QueryLibraryRegistry`'s YAML file ordering rather than being a
reproducible function of the score alone.
"""

from __future__ import annotations

from collections.abc import Sequence

from querymind.query_library.models import QueryExample
from querymind.retrieval.exceptions import InvalidTopKError
from querymind.retrieval.models import RetrievalScore


class ExampleRanker:
    """Ranks `(QueryExample, RetrievalScore)` pairs and returns the top-K, best first."""

    def rank(
        self, scored: Sequence[tuple[QueryExample, RetrievalScore]], top_k: int
    ) -> tuple[tuple[QueryExample, RetrievalScore], ...]:
        """Return the `top_k` highest-scoring pairs, sorted best first.

        Raises `InvalidTopKError` if `top_k` isn't a positive integer.
        """
        if top_k <= 0:
            raise InvalidTopKError(top_k)
        ordered = sorted(scored, key=lambda pair: (-pair[1].overall_score, pair[0].id))
        return tuple(ordered[:top_k])
