"""Builds the final, explainable `RetrievedExample` from a score and a match set.

Every retrieved example must explain why it was selected, which signals
matched, which concepts matched, and which schema matched — this module
is where those four requirements are assembled into one human-readable
`selection_explanation` plus the structured `matched_*` fields, reusing
`querymind.retrieval.matcher.ConceptSchemaKeywordMatcher` so "what
counts as a match" is never recomputed differently here than it was for
scoring.
"""

from __future__ import annotations

from querymind.query_library.models import QueryExample
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher
from querymind.retrieval.models import RetrievalScore, RetrievedExample
from querymind.schema_linker.models import LinkedQueryContext


class ExplanationBuilder:
    """Assembles a `RetrievedExample` from a `RetrievalScore` plus the underlying match data."""

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def build(
        self, context: LinkedQueryContext, example: QueryExample, score: RetrievalScore
    ) -> RetrievedExample:
        matched_concepts = self._matcher.matched_business_concepts(context, example)
        matched_schema = self._matcher.matched_schema_objects(context, example)
        matched_keywords = self._matcher.matched_keywords(context, example)
        return RetrievedExample(
            example=example,
            overall_score=score.overall_score,
            signal_breakdown=score.signal_scores,
            matched_business_concepts=matched_concepts,
            matched_schema_objects=matched_schema,
            matched_keywords=matched_keywords,
            selection_explanation=self._explanation_text(
                score, matched_concepts, matched_schema, matched_keywords
            ),
        )

    @staticmethod
    def _explanation_text(
        score: RetrievalScore,
        matched_concepts: tuple[str, ...],
        matched_schema: tuple[str, ...],
        matched_keywords: tuple[str, ...],
    ) -> str:
        parts = [
            f"Selected with an overall score of {score.overall_score:.2f}.",
            score.ranking_reason,
        ]
        if matched_concepts:
            parts.append(f"Shared business concepts: {', '.join(matched_concepts)}.")
        if matched_schema:
            parts.append(f"Shared schema objects: {', '.join(matched_schema)}.")
        if matched_keywords:
            parts.append(f"Shared keywords: {', '.join(matched_keywords)}.")
        return " ".join(parts)
