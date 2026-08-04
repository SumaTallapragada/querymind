"""Cache abstraction for LLM responses — defined, but deliberately not wired up.

Phase 10B asks for the abstraction only: "Do not cache responses." A
provider's response to a compiled prompt is not generally safe to reuse
silently (temperature > 0 makes generation non-deterministic even for an
identical request, and staleness is a real risk for anything
question-answering-shaped). `NoOpLLMResponseCache` satisfies the
`LLMResponseCache` protocol without caching anything; `LLMAdapter` does
not accept or call a cache at all in this phase — a future phase can
wire a real cache implementation in without changing this abstraction.
"""

from __future__ import annotations

from typing import Protocol

from querymind.llm.models import LLMResponse


class LLMResponseCache(Protocol):
    """Interface for a cache of request key -> `LLMResponse`."""

    def get(self, key: str) -> LLMResponse | None:
        """Return the cached response for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, response: LLMResponse) -> None:
        """Store `response` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpLLMResponseCache:
    """An `LLMResponseCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> LLMResponse | None:
        return None

    def set(self, key: str, response: LLMResponse) -> None:
        return None

    def clear(self) -> None:
        return None
