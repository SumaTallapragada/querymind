from __future__ import annotations

import pytest

from querymind.nlu.filters import DefaultFilterExtractor
from querymind.nlu.models import ComparisonOperator

_EXTRACTOR = DefaultFilterExtractor()


@pytest.mark.parametrize(
    ("question", "expected_operator", "expected_value"),
    [
        ("products with price greater than 50", ComparisonOperator.GREATER_THAN, "50"),
        ("products with price less than 50", ComparisonOperator.LESS_THAN, "50"),
        ("products with price at least 50", ComparisonOperator.GREATER_THAN_OR_EQUAL, "50"),
        ("products with price at most 50", ComparisonOperator.LESS_THAN_OR_EQUAL, "50"),
        ("products with category equals electronics", ComparisonOperator.EQUALS, "electronics"),
    ],
)
def test_extracts_expected_operator_and_value(
    question: str, expected_operator: ComparisonOperator, expected_value: str
) -> None:
    filters = _EXTRACTOR.extract(question)
    assert len(filters) == 1
    assert filters[0].operator is expected_operator
    assert filters[0].value == expected_value


def test_resolves_field_to_the_canonical_business_concept() -> None:
    filters = _EXTRACTOR.extract("products with price greater than 50")
    assert filters[0].field == "price"


def test_returns_empty_tuple_when_field_is_not_a_known_concept() -> None:
    """A comparator with no recognizable field on either side of it produces no filter."""
    filters = _EXTRACTOR.extract("xyzzy greater than 50")
    assert filters == ()


def test_returns_empty_tuple_when_no_comparator_present() -> None:
    assert _EXTRACTOR.extract("show me all products") == ()


def test_finds_multiple_filters_in_order_of_appearance() -> None:
    filters = _EXTRACTOR.extract("products with price greater than 50 and rating at least 4")
    assert [f.field for f in filters] == ["price", "review_rating"]
