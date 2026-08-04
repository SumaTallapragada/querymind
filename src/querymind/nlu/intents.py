"""Intent classification.

Assigns an `Intent` to a normalized question using an ordered set of
keyword/phrase rules, most specific first — e.g. an explicit "top 5"
phrasing is classified `TOP_N` before the generic "total"/"sum" check
for `SUM` gets a chance to misfire on a question that happens to also
mention a number.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Protocol

from querymind.nlu.models import Intent


class IntentMatch(NamedTuple):
    """The classified intent plus how confidently the matching rule fired."""

    intent: Intent
    confidence: float


class IntentClassifier(Protocol):
    """Assigns an `Intent` to a normalized question."""

    def classify(self, normalized_question: str) -> IntentMatch:
        """Return the best-matching `Intent` and a confidence for that match."""
        ...


#: (intent, phrase patterns, confidence-if-matched), checked top to
#: bottom — the first intent with a matching phrase wins. Ordering
#: encodes specificity: e.g. an explicit "top N" phrasing must be
#: checked before the generic superlative check for `MAX`/`MIN`, or
#: "top 5 cheapest products" would be classified `MIN` instead of
#: `TOP_N`. The `MAX`/`MIN` "most"/"least" patterns exclude a preceding
#: "at " so a threshold phrase like "at least 4" (a filter, handled by
#: `querymind.nlu.filters`) doesn't get misread as a MIN-intent
#: superlative.
_RULES: tuple[tuple[Intent, tuple[str, ...], float], ...] = (
    (
        Intent.TOP_N,
        (
            r"\btop\s+\d+\b",
            r"\bbottom\s+\d+\b",
            r"\bfirst\s+\d+\b",
            r"\bbest\s+\d+\b",
            r"\bworst\s+\d+\b",
        ),
        0.95,
    ),
    (
        Intent.TREND,
        (
            r"\btrend\b",
            r"\btrending\b",
            r"\bover time\b",
            r"\bmonth over month\b",
            r"\byear over year\b",
            r"\bgrowth\b",
            r"\bchange over\b",
        ),
        0.9,
    ),
    (
        Intent.COMPARISON,
        (r"\bcompare\b", r"\bcomparison\b", r"\bversus\b", r"\bvs\.?\b", r"\bdifference between\b"),
        0.9,
    ),
    (
        Intent.COUNT,
        (r"\bhow many\b", r"\bcount of\b", r"\bnumber of\b", r"\bcount\b"),
        0.9,
    ),
    (
        Intent.AVERAGE,
        (r"\baverage\b", r"\bavg\b", r"\bmean\b"),
        0.9,
    ),
    (
        Intent.SUM,
        (r"\btotal\b", r"\bsum of\b", r"\bsum\b"),
        0.85,
    ),
    (
        Intent.MAX,
        (
            r"\bmaximum\b",
            r"\bhighest\b",
            r"\bmost expensive\b",
            r"\blargest\b",
            r"(?<!at )\bmost\b",
        ),
        0.85,
    ),
    (
        Intent.MIN,
        (
            r"\bminimum\b",
            r"\blowest\b",
            r"\bcheapest\b",
            r"\bsmallest\b",
            r"(?<!at )\bleast\b",
        ),
        0.85,
    ),
    (
        Intent.AGGREGATION,
        (
            r"\bby region\b",
            r"\bby category\b",
            r"\bby month\b",
            r"\bby year\b",
            r"\bbroken down\b",
            r"\bgroup(?:ed)? by\b",
            r"\bper\b",
        ),
        0.75,
    ),
    (
        Intent.DETAIL,
        (
            r"\bshow me\b",
            r"\bshow\b",
            r"\blist\b",
            r"\bdetails? of\b",
            r"\bwho is\b",
            r"\bwhat is\b",
            r"\bwhich\b",
        ),
        0.6,
    ),
)


class DefaultIntentClassifier:
    """Rule-based `IntentClassifier` checking an ordered list of phrase patterns.

    Falls back to `Intent.SELECT` at low confidence when nothing more
    specific matches — a generic lookup is still a valid, if
    underspecified, question.
    """

    def classify(self, normalized_question: str) -> IntentMatch:
        for intent, patterns, confidence in _RULES:
            for pattern in patterns:
                if re.search(pattern, normalized_question):
                    return IntentMatch(intent=intent, confidence=confidence)
        return IntentMatch(intent=Intent.SELECT, confidence=0.4)
