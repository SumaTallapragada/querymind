"""Domain-specific exceptions for the Prompt Compiler."""

from __future__ import annotations


class PromptCompilerError(Exception):
    """Base class for every exception raised by `querymind.prompt_compiler`."""


class InvalidTokenBudgetError(PromptCompilerError):
    """Raised when a `PromptBudgetManager` is configured with a non-positive `max_tokens`."""

    def __init__(self, max_tokens: int) -> None:
        self.max_tokens = max_tokens
        super().__init__(f"max_tokens must be a positive integer, got {max_tokens!r}.")


class PromptCompilationError(PromptCompilerError):
    """Raised when the pipeline produces an internally inconsistent result (a builder bug).

    Never raised for ordinary content-quality problems — those are
    reported as data by `querymind.prompt_compiler.validator.PromptValidator`,
    never exceptions. This is reserved for invariants the compiler itself
    is responsible for upholding (e.g. a required section missing from
    the section set the pipeline assembled).
    """
