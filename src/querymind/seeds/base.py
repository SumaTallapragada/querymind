"""Reusable seed infrastructure shared by every domain generator.

Defines the common interface every generator implements (`BaseGenerator`),
the shared configuration threaded through all of them (`SeedContext`), and
the abstraction over how generated records eventually get persisted
(`TransactionRunner`). Nothing here generates data or touches a database —
Phase 4 implements `generate()` per domain and `TransactionRunner` against
the async session established in `querymind.db.session` (Phase 1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import Generic, TypeVar

from querymind.models.base import Base
from querymind.seeds.utils import create_seeded_random

ModelT = TypeVar("ModelT", bound=Base)


@dataclass(frozen=True, slots=True)
class SeedContext:
    """Configuration shared across every generator in a single seed run.

    Passed by reference into every `BaseGenerator` instead of threading
    individual keyword arguments (seed, locale, ...) through each domain
    generator's constructor — adding a new cross-cutting setting later
    means changing this one dataclass, not every generator file.
    """

    seed: int = 42
    locale: str = "en_US"


class BaseGenerator(ABC, Generic[ModelT]):
    """Common interface every domain generator implements.

    Subclasses receive the number of records to produce (`count`) and a
    `SeedContext` for shared, cross-cutting configuration. Anything a
    generator needs beyond that — other already-generated records it must
    reference via foreign key, e.g. `OrderGenerator` needing `customers`
    — is passed as an explicit constructor argument (dependency
    injection), never fetched by querying the database directly. That is
    what keeps every generator independently unit-testable with plain
    Python objects as fixtures, with no database or event loop required.
    """

    def __init__(self, count: int, context: SeedContext | None = None) -> None:
        if count < 0:
            raise ValueError("count must be >= 0")
        self.count = count
        self.context = context or SeedContext()
        self.rng: Random = create_seeded_random(self.context.seed)

    @abstractmethod
    def generate(self) -> list[ModelT]:
        """Produce exactly `self.count` in-memory model instances.

        Implemented per domain in Phase 4. Must return plain, unpersisted
        ORM instances — callers (via `TransactionRunner`) are responsible
        for adding and committing them; a generator never opens a session
        itself.
        """
        raise NotImplementedError


class TransactionRunner(ABC):
    """Abstraction over how a batch of generated records gets persisted.

    Kept behind an interface so that generators (and their tests) never
    import `AsyncSession` directly, and so a no-op or in-memory test
    double can stand in during unit tests. Phase 4B implements this
    against the async engine/session factory from `querymind.db.session`
    (see `querymind.seeds.persistence.AsyncSessionTransactionRunner`).

    `persist` is a coroutine: `querymind.db.session` (Phase 1) is
    async-only — `AsyncSession` over `asyncpg`, with no synchronous driver
    anywhere in this codebase — so a synchronous method here could never
    actually reach PostgreSQL without nesting a new event loop inside a
    sync call. Phase 4A's original `def persist` was never exercised
    against a real session (that phase explicitly forbade opening one);
    this is the minimal correction needed to make the interface usable at
    all, not a change to what it represents.
    """

    @abstractmethod
    async def persist(self, records: Sequence[ModelT]) -> None:
        """Persist a batch of generated records within a single transaction."""
        raise NotImplementedError
