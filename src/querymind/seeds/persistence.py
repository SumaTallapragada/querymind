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

    `add_all` runs once for the *entire* batch before `flush` is ever
    called. This matters for large stages: a single stage's records
    routinely share a "hub" parent from an earlier stage (e.g. thousands
    of `Order`s pointing at a few hundred `Customer`s). If a stage were
    flushed in slices — add a slice, flush it, add the next slice, flush
    it — SQLAlchemy would, on each early flush, try to synchronize that
    shared parent's *entire* relationship history, including child
    records from later slices that hadn't been added yet, and correctly
    (if noisily) decline with `SAWarning: Object of type <...> not in
    session, add operation along '<relationship>' won't proceed` for each
    one — deferring, not losing, that synchronization to a later flush
    once the child was finally present. Registering every record with the
    session first, before any flush runs, means no relationship history
    is ever inspected for a child that isn't already attached, so the
    warning's precondition never occurs.

    A single `flush` still bounds actual statement size: SQLAlchemy 2.0's
    `insertmanyvalues` execution strategy (the default for PostgreSQL)
    automatically pages a large bulk insert into multiple appropriately
    sized `INSERT` statements under the hood, which is what the earlier
    manual `batch_size` chunking here was reimplementing by hand — so
    dropping the hand-rolled chunking doesn't trade away that protection.
    One `commit` per `persist()` call is unchanged — one commit per
    generation stage, never one per row.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(self, records: Sequence[ModelT]) -> None:
        self._session.add_all(records)
        await self._session.flush()
        await self._session.commit()
