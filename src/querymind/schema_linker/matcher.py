"""Deterministic concept-to-schema-object matching — the core comparison logic.

Given one business concept string (already normalized by the NLU engine,
e.g. `"customer"`, `"average_order_value"`) and one candidate schema
object's searchable text (its identifier name, plus — for columns —
synonyms, search keywords, and display name), `ConceptMatcher` decides
whether they match and, if so, under which of the six `MatchTier` tiers.
Every comparison is either a normalized string equality check or a
`difflib`-based similarity ratio: both fully deterministic and
reproducible, with no embeddings and no vector search anywhere in this
module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from querymind.schema_linker.models import MatchTier

#: Deterministic abbreviation -> full-word expansions checked by the ALIAS
#: tier. Curated for this schema's vocabulary, not an exhaustive English
#: abbreviation list.
_ABBREVIATIONS: dict[str, str] = {
    "qty": "quantity",
    "amt": "amount",
    "num": "number",
    "id": "identifier",
    "addr": "address",
    "desc": "description",
    "msg": "message",
    "dob": "date of birth",
    "pct": "percent",
    "avg": "average",
    "min": "minimum",
    "max": "maximum",
    "std": "standard",
    "info": "information",
}

#: Minimum `difflib` similarity ratio for a FUZZY match to count at all.
FUZZY_THRESHOLD = 0.75
#: Shortest concept length a PARTIAL (substring) match will consider —
#: below this, containment is too weak a signal to be meaningful (almost
#: any short string is a substring of something).
_PARTIAL_MIN_LENGTH = 3


def normalize_concept(text: str) -> str:
    """Lowercase and collapse underscores to spaces, so `"order_item"` and `"Order Item"` compare equal."""
    return " ".join(text.strip().lower().replace("_", " ").split())


def _singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _pluralize(word: str) -> str:
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def _canonical_alias_tokens(text: str) -> frozenset[str]:
    """Token set for `text` with every abbreviation replaced by its full form.

    Comparing two strings' canonical token sets (rather than the raw
    strings) is what lets `"qty"` match a column named `"quantity"` in
    either direction, and `"dob"` match `"date_of_birth"` — the
    comparison is symmetric because both sides are always expanded
    toward the same full form before comparing.
    """
    tokens = normalize_concept(text).split()
    canonical: set[str] = set()
    for token in tokens:
        canonical.update(_ABBREVIATIONS.get(token, token).split())
    return frozenset(canonical)


@dataclass(frozen=True, slots=True)
class MatchResult:
    """The outcome of one successful `ConceptMatcher.match` call."""

    tier: MatchTier
    #: 1.0 for every exact-equality tier (EXACT/BUSINESS_DICTIONARY/SYNONYM/
    #: ALIAS); the measured similarity ratio for FUZZY/PARTIAL.
    similarity: float
    matched_text: str


class ConceptMatcher:
    """Matches one business concept against one candidate's searchable text, tier by tier.

    Tries tiers in priority order and returns the *first* (highest-
    priority) tier that matches — a concept matching a column's exact
    name is reported as `EXACT`, never additionally as `SYNONYM` or
    `FUZZY` too, even though those might also technically apply. Table
    matching passes only `name`/`synonyms` (tables have no
    `search_keywords`/`display_name` in the Metadata Engine's model);
    column matching passes all four.
    """

    def match(
        self,
        concept: str,
        *,
        name: str,
        synonyms: Sequence[str] = (),
        search_keywords: Sequence[str] = (),
        display_name: str | None = None,
    ) -> MatchResult | None:
        normalized_concept = normalize_concept(concept)
        concept_forms = {
            normalized_concept,
            normalize_concept(_singularize(concept)),
            normalize_concept(_pluralize(concept)),
        }
        normalized_name = normalize_concept(name)

        if normalized_name in concept_forms:
            return MatchResult(MatchTier.EXACT, 1.0, name)

        dictionary_forms = {normalize_concept(term) for term in search_keywords}
        if display_name is not None:
            dictionary_forms.add(normalize_concept(display_name))
        dictionary_hit = concept_forms & dictionary_forms
        if dictionary_hit:
            return MatchResult(MatchTier.BUSINESS_DICTIONARY, 1.0, next(iter(dictionary_hit)))

        synonym_forms = {normalize_concept(term) for term in synonyms}
        synonym_hit = concept_forms & synonym_forms
        if synonym_hit:
            return MatchResult(MatchTier.SYNONYM, 1.0, next(iter(synonym_hit)))

        if _canonical_alias_tokens(concept) == _canonical_alias_tokens(name):
            return MatchResult(MatchTier.ALIAS, 1.0, name)

        searchable_texts = (
            name,
            *synonyms,
            *search_keywords,
            *((display_name,) if display_name else ()),
        )

        best_fuzzy_ratio = max(
            (
                SequenceMatcher(None, normalized_concept, normalize_concept(text)).ratio()
                for text in searchable_texts
            ),
            default=0.0,
        )
        if best_fuzzy_ratio >= FUZZY_THRESHOLD:
            return MatchResult(MatchTier.FUZZY, best_fuzzy_ratio, name)

        if len(normalized_concept) >= _PARTIAL_MIN_LENGTH:
            partial_ratio = self._best_partial_ratio(normalized_concept, searchable_texts)
            if partial_ratio is not None:
                return MatchResult(MatchTier.PARTIAL, partial_ratio, name)

        return None

    @staticmethod
    def _best_partial_ratio(
        normalized_concept: str, searchable_texts: Sequence[str]
    ) -> float | None:
        """The best containment ratio among `searchable_texts` that contains (or is contained by) the concept."""
        best: float | None = None
        for text in searchable_texts:
            normalized_text = normalize_concept(text)
            if normalized_concept in normalized_text or normalized_text in normalized_concept:
                ratio = min(len(normalized_concept), len(normalized_text)) / max(
                    len(normalized_concept), len(normalized_text)
                )
                if best is None or ratio > best:
                    best = ratio
        return best
