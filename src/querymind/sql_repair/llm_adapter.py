"""A lightweight wrapper around the existing `LLMAdapter` — never a second provider layer.

`SQLRepairLLMAdapter`'s only responsibility is calling
`LLMAdapter.generate()` with a repair `CompiledPrompt`. It knows nothing
about providers, retries, or metrics collection — `LLMAdapter` already
owns all of that.
"""

from __future__ import annotations

from querymind.llm.adapter import LLMAdapter
from querymind.llm.models import LLMResponse
from querymind.prompt_compiler.models import CompiledPrompt


class SQLRepairLLMAdapter:
    """Calls the existing `LLMAdapter` with a repair prompt. Nothing more."""

    def __init__(self, llm_adapter: LLMAdapter) -> None:
        self._llm_adapter = llm_adapter

    def repair(self, prompt: CompiledPrompt) -> LLMResponse:
        """Send `prompt` (a repair `CompiledPrompt`) to the existing `LLMAdapter` and return its response."""
        return self._llm_adapter.generate(prompt)
