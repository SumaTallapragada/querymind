"""`AuditLogger` -- writes one security-relevant event to both the real `structlog` pipeline
(`querymind.core.logging.get_logger()` -- the actual stdout/JSON pipeline every request already
goes through, deliberately *not* `querymind.observability.logger.StructuredLogger`'s default
`InMemoryLogSink`, which nothing in production ever reads) and a durable `AuditLog` row via
`AuditRepository` (queryable compliance history that survives log rotation or an unconfigured
aggregator). Both, not either -- see the Phase 22D design notes for why.

Never raises from a failed audit write: a security event's own persistence must never become a
new way for the request that triggered it (a login, a query) to fail. A database hiccup while
writing an audit row logs a warning and moves on; it does not turn an otherwise-successful login
into a `500`.

Every field this module accepts is already a safe, pre-extracted primitive (a username string,
an IP, a capped user-agent, an event-type enum value) -- there is no code path here that could
serialize a password, JWT, refresh token, raw API key, or `Authorization` header, because none
of those is ever passed in. Callers (routes, `querymind.api.exception_handlers`) are responsible
for that boundary; this class enforces nothing beyond what its own parameter list allows in.
"""

from __future__ import annotations

from enum import Enum

from querymind.core.logging import get_logger
from querymind.security.repository import AuditRepository

_MAX_USER_AGENT_LENGTH = 300


class AuditEventType(str, Enum):
    """Every security-relevant event Phase 22D records. Values are both the literal
    `AuditLog.event_type` string persisted and the structlog event name emitted.
    """

    REGISTRATION = "registration"
    REGISTRATION_FAILURE = "registration_failure"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    REFRESH_SUCCESS = "refresh_success"
    REFRESH_FAILURE = "refresh_failure"
    LOGOUT = "logout"
    AUTHORIZATION_DENIED = "authorization_denied"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_AUTH_SUCCESS = "api_key_auth_success"
    API_KEY_AUTH_FAILURE = "api_key_auth_failure"


class AuditLogger:
    """Constructor-injected `AuditRepository` -- no global/module-level logger instance,
    mirroring `querymind.observability.logger`'s own "no singleton loggers" rule.
    """

    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository
        self._logger = get_logger(component="audit")

    async def record(
        self,
        event_type: AuditEventType,
        *,
        success: bool,
        actor_user_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        resource: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Record one event. `success=False` logs at `WARNING` (structlog) so a log-based alert
        can key off severity alone, without parsing `event_type`; `success=True` logs at `INFO`.
        """
        log = self._logger.info if success else self._logger.warning
        log(
            event_type.value,
            success=success,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            ip_address=ip_address,
            resource=resource,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        try:
            await self._repository.create(
                event_type=event_type.value,
                success=success,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                ip_address=ip_address,
                user_agent=user_agent[:_MAX_USER_AGENT_LENGTH] if user_agent else None,
                request_id=request_id,
                correlation_id=correlation_id,
                resource=resource,
                event_metadata=metadata,
            )
        except Exception:
            # Best-effort, deliberately: see this module's own docstring for why an audit-write
            # failure must never fail the request that triggered it.
            self._logger.warning("audit_log_write_failed", event_type=event_type.value)
