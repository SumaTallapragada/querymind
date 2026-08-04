from __future__ import annotations

import pytest

from querymind.nlu.limits import DefaultLimitExtractor

_EXTRACTOR = DefaultLimitExtractor()


@pytest.mark.parametrize(
    "question",
    [
        "show the top 10 customers",
        "show the first 10 customers",
        "show the bottom 10 customers",
        "show the last 10 customers",
        "limit 10",
    ],
)
def test_extracts_the_stated_count(question: str) -> None:
    limit = _EXTRACTOR.extract(question)
    assert limit is not None
    assert limit.value == 10


def test_returns_none_when_no_number_stated() -> None:
    """Never guesses a default — see the module docstring."""
    assert _EXTRACTOR.extract("show the top customers") is None


def test_returns_none_when_no_limit_phrase_present() -> None:
    assert _EXTRACTOR.extract("show all customers") is None
