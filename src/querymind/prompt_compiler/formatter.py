"""Assembles a `CompiledPrompt`'s sections into a single prompt string.

The one place that concatenates section text — no section builder ever
does this itself (each only produces its own `content` string; how those
strings get joined, in what order, under what headers, is entirely this
class's job, driven by a `PromptTemplate`).
"""

from __future__ import annotations

from querymind.prompt_compiler.models import CompiledPrompt
from querymind.prompt_compiler.templates import DefaultPromptTemplate, PromptTemplate


class PromptFormatter:
    """Renders a `CompiledPrompt` into one string, per a `PromptTemplate`'s ordering and headers."""

    def __init__(self, template: PromptTemplate | None = None) -> None:
        self._template = template or DefaultPromptTemplate()

    def format(self, prompt: CompiledPrompt) -> str:
        """Return `prompt` as one string: each non-empty section's header, then its content, in template order."""
        sections_by_name = {section.name: section for section in prompt.all_sections()}
        parts: list[str] = []
        for name in self._template.ordered_names():
            section = sections_by_name.get(name)
            if section is None or not section.content.strip():
                continue
            spec = self._template.spec_for(name)
            parts.append(f"{spec.header}\n{section.content.strip()}")
        return "\n\n".join(parts)
