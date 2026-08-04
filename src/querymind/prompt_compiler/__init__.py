"""The Prompt Compiler — QueryMind Phase 10A.

Converts a `querymind.retrieval.RetrievedKnowledgeBundle` into a
`CompiledPrompt`: seven independently built sections (system, business
context, schema context, relationships, retrieved examples, constraints,
output format), validated, trimmed to fit a token budget, and assembled
into one immutable model with a `.as_text()` rendering.

This is **not** an LLM client — it does not call a model, does not
generate SQL, and knows nothing about Claude, OpenAI, Gemini, Ollama, or
any other provider. That integration is a later phase (the LLM Adapter)
this package deliberately stops short of.

The public surface is `PromptCompiler.compile`.
"""

from __future__ import annotations

from querymind.prompt_compiler.budget import DEFAULT_MAX_TOKENS, PromptBudgetManager
from querymind.prompt_compiler.cache import InMemoryPromptCache, PromptCache
from querymind.prompt_compiler.compiler import PromptCompiler
from querymind.prompt_compiler.exceptions import (
    InvalidTokenBudgetError,
    PromptCompilationError,
    PromptCompilerError,
)
from querymind.prompt_compiler.formatter import PromptFormatter
from querymind.prompt_compiler.models import (
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptSection,
    PromptStatistics,
    RelationshipSection,
    SchemaSection,
    SectionName,
    SystemSection,
)
from querymind.prompt_compiler.serializer import PromptCompilerSerializer
from querymind.prompt_compiler.templates import DefaultPromptTemplate, PromptTemplate, SectionSpec
from querymind.prompt_compiler.validator import PromptValidationReport, PromptValidator

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "BusinessSection",
    "CompiledPrompt",
    "ConstraintSection",
    "DefaultPromptTemplate",
    "ExampleSection",
    "InMemoryPromptCache",
    "InvalidTokenBudgetError",
    "OutputSection",
    "PromptBudgetManager",
    "PromptCache",
    "PromptCompilationError",
    "PromptCompiler",
    "PromptCompilerError",
    "PromptCompilerSerializer",
    "PromptFormatter",
    "PromptSection",
    "PromptStatistics",
    "PromptTemplate",
    "PromptValidationReport",
    "PromptValidator",
    "RelationshipSection",
    "SchemaSection",
    "SectionName",
    "SectionSpec",
    "SystemSection",
]
