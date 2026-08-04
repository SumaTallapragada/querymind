from __future__ import annotations

from querymind.nlu.normalizer import DefaultNormalizer


def test_lowercases_and_strips_trailing_punctuation() -> None:
    assert DefaultNormalizer().normalize("What is Total Revenue?") == "what is total revenue"


def test_collapses_repeated_whitespace() -> None:
    assert DefaultNormalizer().normalize("show   me   orders") == "show me orders"


def test_expands_common_contractions() -> None:
    assert DefaultNormalizer().normalize("What's the total revenue?") == "what is the total revenue"


def test_strips_leading_and_trailing_surrounding_whitespace() -> None:
    assert DefaultNormalizer().normalize("  show orders  ") == "show orders"
