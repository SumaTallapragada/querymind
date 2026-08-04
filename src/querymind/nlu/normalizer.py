"""Question normalization — the first pipeline stage.

Produces a lowercase, whitespace-collapsed, punctuation-trimmed form of
the question for every later stage to match patterns against, so no
downstream stage needs its own ad hoc case-folding or contraction
handling.
"""

from __future__ import annotations

import re
from typing import Protocol

#: Common contractions expanded before matching, so a rule only has to
#: know about "is not", never "isn't" as well.
_CONTRACTIONS: dict[str, str] = {
    "what's": "what is",
    "who's": "who is",
    "how's": "how is",
    "where's": "where is",
    "let's": "let us",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "can't": "cannot",
    "won't": "will not",
    "i'm": "i am",
    "it's": "it is",
    "there's": "there is",
}

_WHITESPACE_PATTERN = re.compile(r"\s+")
_TRAILING_PUNCTUATION_PATTERN = re.compile(r"[?!.]+$")


class Normalizer(Protocol):
    """Reduces a raw question to a canonical form later pipeline stages match against."""

    def normalize(self, question: str) -> str:
        """Return the normalized form of `question`."""
        ...


class DefaultNormalizer:
    """Lowercases, expands common contractions, and collapses whitespace/punctuation."""

    def normalize(self, question: str) -> str:
        text = question.strip().lower()
        text = _TRAILING_PUNCTUATION_PATTERN.sub("", text)
        for contraction, expansion in _CONTRACTIONS.items():
            text = re.sub(rf"\b{re.escape(contraction)}\b", expansion, text)
        text = _WHITESPACE_PATTERN.sub(" ", text)
        return text.strip()
