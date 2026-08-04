from __future__ import annotations

from querymind.nlu.entities import DefaultEntityExtractor

_EXTRACTOR = DefaultEntityExtractor()


def test_finds_primary_entity() -> None:
    result = _EXTRACTOR.extract("show me the top customers")
    assert result.primary_entity == "customer"


def test_finds_secondary_entities_in_order_of_appearance() -> None:
    result = _EXTRACTOR.extract("show orders and their payments")
    assert result.primary_entity == "order"
    assert result.secondary_entities == ("payment",)


def test_returns_none_primary_entity_when_nothing_recognized() -> None:
    result = _EXTRACTOR.extract("what is the total revenue")
    assert result.primary_entity is None
    assert result.secondary_entities == ()


def test_resolves_synonyms_to_the_same_canonical_entity() -> None:
    assert _EXTRACTOR.extract("show clients").primary_entity == "customer"
    assert _EXTRACTOR.extract("show buyers").primary_entity == "customer"


def test_longer_phrase_wins_over_the_shorter_phrase_nested_inside_it() -> None:
    """ "product category" must resolve to "category", not "product"."""
    result = _EXTRACTOR.extract("show product categories")
    assert result.primary_entity == "category"


def test_finds_dimensions() -> None:
    result = _EXTRACTOR.extract("compare revenue between regions and states")
    assert result.dimensions == ("region", "state")


def test_dimensions_do_not_include_calendar_words() -> None:
    """ "month"/"year"/"quarter" are owned by `querymind.nlu.time`, not dimensions."""
    result = _EXTRACTOR.extract("revenue this month and this year")
    assert result.dimensions == ()
