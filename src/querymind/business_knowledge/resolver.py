"""Deterministic business-term resolution: exact, alias, synonym, partial.

`ConceptResolver` is what `querymind.business_knowledge.registry.
BusinessKnowledgeRegistry.resolve`/`resolve_many` delegate to. Given one
business term (typically drawn from a `QueryContext`'s
`business_concepts`, `metrics`, `dimensions`, or a filter field), it
checks every concept in the catalog against four deterministic tiers, in
priority order, and returns the first match. No embeddings, no LLM, and
— deliberately, unlike the Schema Linker's resolver — no confidence
scoring or ambiguity ranking: this is a lighter terminology lookup, not
a full disambiguation engine.
"""

from __future__ import annotations

from collections.abc import Iterable

from querymind.business_knowledge.models import BusinessConcept, BusinessKnowledgeCatalog

#: Shortest normalized term a PARTIAL (substring) match will consider —
#: below this, containment is too weak a signal to be meaningful (almost
#: any short string is a substring of something).
_PARTIAL_MIN_LENGTH = 3


def _normalize(text: str) -> str:
    """Lowercase and collapse underscores/whitespace, so `"order_value"` and `"Order Value"` compare equal."""
    return " ".join(text.strip().lower().replace("_", " ").split())


class ConceptResolver:
    """Resolves business terms to `BusinessConcept`s from one loaded catalog.

    Built from a `BusinessKnowledgeCatalog` snapshot (not a live
    registry), so it stays a small, pure, easily-testable unit —
    `BusinessKnowledgeRegistry` is what constructs a fresh one on
    `refresh()`.
    """

    def __init__(self, catalog: BusinessKnowledgeCatalog) -> None:
        self._concepts = catalog.concepts

    def resolve(self, term: str) -> BusinessConcept | None:
        """Resolve one business term to its matching concept, or `None`.

        Checked in priority order across the *whole* catalog at each
        tier before moving to the next: every concept's canonical
        `name` is checked for an EXACT match first; only if none match
        does every concept's `aliases` get checked (ALIAS), then
        `related_terms` (SYNONYM), then substring containment
        (PARTIAL). Ties within a tier are broken by catalog order — the
        order concepts appear in `concepts.yaml`.
        """
        normalized_term = _normalize(term)

        for concept in self._concepts:
            if _normalize(concept.name) == normalized_term:
                return concept

        for concept in self._concepts:
            if any(_normalize(alias.text) == normalized_term for alias in concept.aliases):
                return concept

        for concept in self._concepts:
            if any(_normalize(related) == normalized_term for related in concept.related_terms):
                return concept

        if len(normalized_term) >= _PARTIAL_MIN_LENGTH:
            for concept in self._concepts:
                if self._partially_matches(normalized_term, concept):
                    return concept

        return None

    def resolve_many(self, terms: Iterable[str]) -> tuple[BusinessConcept, ...]:
        """Resolve every term in `terms`, skipping any that don't match anything.

        Deduplicates by concept `id`, in first-resolved order — resolving
        `("aov", "average order value")` (two names for the same
        concept) returns that concept once.
        """
        seen: set[str] = set()
        resolved: list[BusinessConcept] = []
        for term in terms:
            concept = self.resolve(term)
            if concept is not None and concept.id not in seen:
                seen.add(concept.id)
                resolved.append(concept)
        return tuple(resolved)

    @staticmethod
    def _partially_matches(normalized_term: str, concept: BusinessConcept) -> bool:
        """Substring-containment check against the concept's *own* vocabulary only.

        Deliberately excludes `related_terms`: those are other concepts'
        names, referenced here as loose associations, not this
        concept's own vocabulary — including them would let a term
        partially match concept A merely because concept B happens to
        reference A's name in its `related_terms`, even when B has
        nothing to do with the term itself.
        """
        candidates = (concept.name, *(alias.text for alias in concept.aliases))
        for candidate in candidates:
            normalized_candidate = _normalize(candidate)
            if normalized_term in normalized_candidate or normalized_candidate in normalized_term:
                return True
        return False
