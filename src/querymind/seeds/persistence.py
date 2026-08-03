"""Concrete `TransactionRunner`: batched persistence through one shared `AsyncSession`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from querymind.seeds.base import ModelT, TransactionRunner


class AsyncSessionTransactionRunner(TransactionRunner):
    """Persists generated ORM objects through one shared `AsyncSession`.

    Constructed with a single session that lives for the whole generation
    run (see `scripts/seed_database.py`) — not one session per stage — so
    that objects persisted in an earlier stage (e.g. `Customer`) stay
    attached to the same identity map and can be referenced by later
    stages via ORM relationships (`order.customer = customer`) without
    ever needing to re-fetch or manually read back a not-yet-existent
    primary key.

    Batches `add_all` + `flush` in chunks of `batch_size` to bound peak
    statement size for large record counts (e.g. 100,000+ orders), then
    issues one `commit` per `persist()` call — one commit per generation
    stage, never one per row.
    """

    def __init__(self, session: AsyncSession, batch_size: int = 2_000) -> None:
        self._session = session
        self._batch_size = batch_size

    async def persist(self, records: Sequence[ModelT]) -> None:
        for start in range(0, len(records), self._batch_size):
            batch = records[start : start + self._batch_size]
            self._session.add_all(batch)
            await self._session.flush()
        await self._session.commit()
