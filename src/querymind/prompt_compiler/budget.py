"""Approximate token counting and token-budget enforcement.

`estimate_tokens` is a deterministic, provider-agnostic heuristic (~4
characters per token, a commonly cited rule of thumb for English text) —
not a real tokenizer. Using an actual tokenizer (e.g. `tiktoken`) would
tie this package to a specific model provider's vocabulary, which the
Prompt Compiler is explicitly forbidden from knowing about. "Approximate
token counting is acceptable" is exactly this trade-off.

`PromptBudgetManager` is what enforces the requested trim order (retrieved
examples first, then schema context, then business context) when a
compiled prompt's total estimated tokens exceed the budget — trimming a
section's `content` down to size before dropping it entirely, and never
touching a required section.
"""

from __future__ import annotations

from collections.abc import Sequence

from querymind.prompt_compiler.exceptions import InvalidTokenBudgetError
from querymind.prompt_compiler.models import PromptSection

#: The default maximum prompt budget, in estimated tokens.
DEFAULT_MAX_TOKENS = 4000

#: Characters per token in the approximate counting heuristic.
_CHARS_PER_TOKEN = 4

#: Appended to a section's content when it has been shortened to fit the
#: budget, so a reader (human or model) knows the section was cut, not
#: that this is the whole of what was found.
_TRUNCATION_MARKER = "\n...[truncated to fit token budget]"


def estimate_tokens(text: str) -> int:
    """Approximate the token count of `text` — `len(text) / 4`, rounded up."""
    if not text:
        return 0
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


class PromptBudgetManager:
    """Enforces a maximum total token budget across a set of `PromptSection`s.

    Required sections (`is_required=True`) are always returned
    unchanged, in full, regardless of budget — trimming only ever
    touches non-required sections, in ascending `priority` order (the
    requested "1. retrieved examples, 2. schema context, 3. business
    context" trim order is encoded directly as those sections'
    `priority` values — see `querymind.prompt_compiler.models`).
    """

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        if max_tokens <= 0:
            raise InvalidTokenBudgetError(max_tokens)
        self._max_tokens = max_tokens

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def enforce(self, sections: Sequence[PromptSection]) -> tuple[PromptSection, ...]:
        """Return `sections` (same order), trimming non-required ones as needed to fit `max_tokens`.

        If the required sections alone already exceed `max_tokens`, every
        non-required section is trimmed to empty and the result still
        exceeds budget — no amount of trimming a section that was never
        the problem can fix that; `PromptValidator`'s token-budget rule
        is what surfaces this as a validation error.
        """
        total = sum(section.estimated_tokens for section in sections)
        if total <= self._max_tokens:
            return tuple(sections)

        working = {section.name: section for section in sections}
        trim_order = sorted(
            (section for section in sections if not section.is_required),
            key=lambda section: section.priority,
        )

        for section in trim_order:
            if total <= self._max_tokens:
                break
            excess = total - self._max_tokens
            trimmed, freed = self._shrink_or_drop(section, excess)
            working[section.name] = trimmed
            total -= freed

        return tuple(working[section.name] for section in sections)

    @staticmethod
    def _shrink_or_drop(section: PromptSection, excess_tokens: int) -> tuple[PromptSection, int]:
        """Shrink `section` to free up to `excess_tokens`, or drop it entirely if that's not enough.

        Dropping a section resets any extra structured field it carries
        beyond the base `PromptSection` shape (`ExampleSection.example_ids`,
        `SchemaSection.schema_objects`) to empty too — once `content` is
        cleared, none of what those fields listed is still present, so
        statistics/validation must not keep counting it. A *partial*
        truncation, by contrast, leaves those fields as-is: trimming only
        ever removes text, it can never introduce a duplicate that
        `PromptValidator`'s pre-trim pass didn't already rule out, so the
        original counts remain a reasonable approximation — consistent
        with token counting itself being approximate in this package.
        """
        if excess_tokens >= section.estimated_tokens:
            reset_extras = {
                field: ()
                for field in ("example_ids", "schema_objects")
                if field in type(section).model_fields
            }
            dropped = section.model_copy(
                update={"content": "", "estimated_tokens": 0, **reset_extras}
            )
            return dropped, section.estimated_tokens

        target_tokens = max(0, section.estimated_tokens - excess_tokens)
        target_chars = target_tokens * _CHARS_PER_TOKEN
        truncated_content = section.content[:target_chars].rstrip() + _TRUNCATION_MARKER
        new_tokens = estimate_tokens(truncated_content)
        freed = max(0, section.estimated_tokens - new_tokens)
        shrunk = section.model_copy(
            update={"content": truncated_content, "estimated_tokens": new_tokens}
        )
        return shrunk, freed
