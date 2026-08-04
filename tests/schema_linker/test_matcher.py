from __future__ import annotations

from querymind.schema_linker.matcher import ConceptMatcher
from querymind.schema_linker.models import MatchTier

_MATCHER = ConceptMatcher()


def test_exact_match_on_name() -> None:
    result = _MATCHER.match("customer", name="customers")
    assert result is not None
    assert result.tier is MatchTier.EXACT


def test_exact_match_is_singular_plural_insensitive() -> None:
    assert _MATCHER.match("orders", name="order") is not None
    assert _MATCHER.match("category", name="categories") is not None


def test_exact_match_normalizes_underscores() -> None:
    result = _MATCHER.match("order_item", name="Order Item")
    assert result is not None
    assert result.tier is MatchTier.EXACT


def test_business_dictionary_match_on_search_keywords() -> None:
    result = _MATCHER.match("total", name="total_amount", search_keywords=("total", "grand total"))
    assert result is not None
    assert result.tier is MatchTier.BUSINESS_DICTIONARY


def test_business_dictionary_match_on_display_name() -> None:
    """Matches via `display_name`, distinct from the column's own (differently spelled) `name`."""
    result = _MATCHER.match("total amount", name="amt", display_name="Total Amount")
    assert result is not None
    assert result.tier is MatchTier.BUSINESS_DICTIONARY


def test_synonym_match() -> None:
    result = _MATCHER.match("revenue", name="total_amount", synonyms=("revenue", "order total"))
    assert result is not None
    assert result.tier is MatchTier.SYNONYM


def test_alias_match_on_abbreviation() -> None:
    result = _MATCHER.match("quantity", name="qty")
    assert result is not None
    assert result.tier is MatchTier.ALIAS


def test_alias_match_is_symmetric() -> None:
    """The concept can use the abbreviation while the column spells it out, or vice versa."""
    assert _MATCHER.match("qty", name="quantity") is not None
    assert _MATCHER.match("quantity", name="qty") is not None


def test_fuzzy_match_on_near_miss_spelling() -> None:
    result = _MATCHER.match("custommer", name="customer")
    assert result is not None
    assert result.tier is MatchTier.FUZZY


def test_partial_match_on_substring() -> None:
    result = _MATCHER.match("amount", name="total_amount")
    assert result is not None
    assert result.tier is MatchTier.PARTIAL


def test_partial_match_requires_a_minimum_length() -> None:
    """A 1-2 character concept is too weak a signal for substring matching."""
    assert _MATCHER.match("id", name="valid") is None


def test_no_match_returns_none() -> None:
    assert (
        _MATCHER.match("revenue", name="lead_time_days", synonyms=("delivery lead time",)) is None
    )


def test_higher_priority_tier_wins_over_a_lower_one() -> None:
    """A concept that would also fuzzy-match must still be reported at its best (exact) tier."""
    result = _MATCHER.match("order", name="order", synonyms=("purchases",))
    assert result is not None
    assert result.tier is MatchTier.EXACT
