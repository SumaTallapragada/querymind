"""`AuditRepository` -- persistence only, insert-only, mirrors `querymind.auth.repository
.AuthenticationRepository`'s shape exactly (a session factory held once, a short-lived session
per call). No business logic: it does not decide *whether* an event is worth recording or *what*
belongs in it -- that is `AuditLogger`'s job entirely, the same "repository is dumb persistence"
split every other repository in this project already follows.

Deliberately has no `update`/`delete` method at all: an audit record is never mutated or removed
by application code once written -- there is nothing here that *could* tamper with one.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.db.session import transactional_session
from querymind.security.models import AuditLog


class AuditRepository:
    """Insert-only persistence for `AuditLog` rows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, **fields: object) -> AuditLog:
        async with transactional_session(self._session_factory) as session:
            record = AuditLog(**fields)
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return record
