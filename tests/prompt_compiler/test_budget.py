"""Tests for `querymind.prompt_compiler.budget`."""

from __future__ import annotations

import pytest

from querymind.prompt_compiler.budget import (
    DEFAULT_MAX_TOKENS,
    PromptBudgetManager,
    estimate_tokens,
)
from querymind.prompt_compiler.exceptions import InvalidTokenBudgetError
from querymind.prompt_compiler.models import (
    BusinessSection,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptSection,
    SchemaSection,
    SystemSection,
)


class TestEstimateTokens:
    def test_empty_text_is_zero_tokens(self) -> None:
        assert estimate_tokens("") == 0

    def test_rounds_up_to_the_nearest_token(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcde") == 2

    def test_roughly_four_characters_per_token(self) -> None:
        assert estimate_tokens("a" * 400) == 100


class TestPromptBudgetManagerConstruction:
    def test_default_max_tokens(self) -> None:
        manager = PromptBudgetManager()
        assert manager.max_tokens == DEFAULT_MAX_TOKENS

    @pytest.mark.parametrize("bad_value", [0, -1, -100])
    def test_rejects_non_positive_max_tokens(self, bad_value: int) -> None:
        with pytest.raises(InvalidTokenBudgetError):
            PromptBudgetManager(bad_value)


class TestEnforceUnderBudget:
    def test_returns_sections_unchanged_when_under_budget(self) -> None:
        manager = PromptBudgetManager(4000)
        sections = (
            SystemSection(content="sys", estimated_tokens=10),
            BusinessSection(content="biz", estimated_tokens=10),
        )
        result = manager.enforce(sections)
        assert result == sections

    def test_preserves_input_order(self) -> None:
        manager = PromptBudgetManager(4000)
        sections = (
            ConstraintSection(content="con", estimated_tokens=1),
            SystemSection(content="sys", estimated_tokens=1),
        )
        result = manager.enforce(sections)
        assert [s.name for s in result] == [s.name for s in sections]


def _trimmable_sections() -> tuple[PromptSection, ...]:
    """system=10, business=100, schema=100, examples=100, constraint=10, output=10 (total 330).

    The trimmable sections use 400-char content (100 tokens) so a partial
    truncation actually reduces the token count -- with short content the
    fixed-size truncation marker can cost more tokens than trimming saves.
    """
    return (
        SystemSection(content="S" * 40, estimated_tokens=10),
        BusinessSection(content="B" * 400, estimated_tokens=100),
        SchemaSection(content="C" * 400, estimated_tokens=100, schema_objects=("t1", "t2")),
        ExampleSection(content="E" * 400, estimated_tokens=100, example_ids=("e1", "e2")),
        ConstraintSection(content="K" * 40, estimated_tokens=10),
        OutputSection(content="O" * 40, estimated_tokens=10),
    )


class TestEnforceTrimOrder:
    def test_examples_trimmed_before_schema_and_business(self) -> None:
        # excess = 30 -> examples (priority 1) shrinks from 100 to 79; schema/business untouched.
        manager = PromptBudgetManager(300)
        result = manager.enforce(_trimmable_sections())
        by_name = {s.name.value: s for s in result}
        assert by_name["retrieved_examples"].estimated_tokens == 79
        assert by_name["schema_context"].estimated_tokens == 100
        assert by_name["business_context"].estimated_tokens == 100

    def test_examples_fully_dropped_before_schema_is_touched(self) -> None:
        # excess = 100 -> exactly examples' own size -> dropped whole; schema/business untouched.
        manager = PromptBudgetManager(230)
        result = manager.enforce(_trimmable_sections())
        by_name = {s.name.value: s for s in result}
        example = next(s for s in result if isinstance(s, ExampleSection))
        assert by_name["retrieved_examples"].estimated_tokens == 0
        assert example.example_ids == ()
        assert by_name["schema_context"].estimated_tokens == 100
        assert by_name["business_context"].estimated_tokens == 100

    def test_schema_dropped_after_examples_before_business(self) -> None:
        manager = PromptBudgetManager(130)
        result = manager.enforce(_trimmable_sections())
        by_name = {s.name.value: s for s in result}
        schema = next(s for s in result if isinstance(s, SchemaSection))
        assert by_name["retrieved_examples"].estimated_tokens == 0
        assert by_name["schema_context"].estimated_tokens == 0
        assert schema.schema_objects == ()
        assert by_name["business_context"].estimated_tokens == 100

    def test_required_sections_are_never_trimmed_even_under_extreme_pressure(self) -> None:
        manager = PromptBudgetManager(1)
        result = manager.enforce(_trimmable_sections())
        by_name = {s.name.value: s for s in result}
        assert by_name["system"].estimated_tokens == 10
        assert by_name["constraint"].estimated_tokens == 10
        assert by_name["output_format"].estimated_tokens == 10

    def test_business_is_the_last_resort(self) -> None:
        manager = PromptBudgetManager(1)
        result = manager.enforce(_trimmable_sections())
        by_name = {s.name.value: s for s in result}
        assert by_name["retrieved_examples"].estimated_tokens == 0
        assert by_name["schema_context"].estimated_tokens == 0
        assert by_name["business_context"].estimated_tokens == 0


class TestShrinkOrDropStructuredFields:
    def test_dropping_a_schema_section_clears_schema_objects(self) -> None:
        manager = PromptBudgetManager(130)
        result = manager.enforce(_trimmable_sections())
        schema = next(s for s in result if isinstance(s, SchemaSection))
        assert schema.content == ""
        assert schema.schema_objects == ()

    def test_dropping_an_example_section_clears_example_ids(self) -> None:
        manager = PromptBudgetManager(230)
        result = manager.enforce(_trimmable_sections())
        example = next(s for s in result if isinstance(s, ExampleSection))
        assert example.content == ""
        assert example.example_ids == ()

    def test_partial_truncation_preserves_structured_fields(self) -> None:
        manager = PromptBudgetManager(300)
        result = manager.enforce(_trimmable_sections())
        example = next(s for s in result if isinstance(s, ExampleSection))
        assert example.content != ""
        assert example.content != "E" * 400
        assert example.example_ids == ("e1", "e2")
