"""In-memory cache for compiled prompts.

Keyed by `(bundle content hash, template version, dialect)` — the three
things that fully determine a compiled prompt's content. Deliberately
does **not** cache invalid prompts (`PromptCompiler` only ever calls
`set()` after `PromptValidator` confirms `is_valid`) — a cache entry is
only ever a prompt safe to reuse.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from querymind.prompt_compiler.models import CompiledPrompt
from querymind.retrieval.models import RetrievedKnowledgeBundle

#: `(bundle_content_hash, template_version, dialect)`.
CacheKey = tuple[str, str, str]


def bundle_content_hash(bundle: RetrievedKnowledgeBundle) -> str:
    """A deterministic hash of the parts of `bundle` that affect a compiled prompt's content.

    Deliberately excludes `bundle.statistics` (retrieval latency, ...) —
    those vary from run to run for reasons that have nothing to do with
    what the prompt should say, and including them would mean the cache
    almost never hits for what is otherwise an identical retrieval.
    """
    payload = {
        "linked_query_context": bundle.linked_query_context.model_dump(mode="json"),
        "retrieved_examples": [
            example.model_dump(mode="json") for example in bundle.retrieved_examples
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PromptCache(Protocol):
    """Interface for a cache of `CacheKey -> CompiledPrompt`."""

    def get(self, key: CacheKey) -> CompiledPrompt | None:
        """Return the cached prompt for `key`, or `None` if not cached."""
        ...

    def set(self, key: CacheKey, prompt: CompiledPrompt) -> None:
        """Store `prompt` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class InMemoryPromptCache:
    """The default `PromptCache`: a plain `dict` held in process memory. No Redis, no TTL."""

    def __init__(self) -> None:
        self._store: dict[CacheKey, CompiledPrompt] = {}

    def get(self, key: CacheKey) -> CompiledPrompt | None:
        return self._store.get(key)

    def set(self, key: CacheKey, prompt: CompiledPrompt) -> None:
        self._store[key] = prompt

    def clear(self) -> None:
        self._store.clear()
