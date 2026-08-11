"""Unit tests for `AuditLogger` -- in isolation, against a fake repository and a fake structlog
logger, mirroring `tests/auth/test_service.py`'s "fake repository, no I/O" precedent for
`AuthenticationService`. `tests/api/test_audit_logging.py` covers the HTTP-level wiring (which
event fires for which route, with which real fields); this file covers `AuditLogger` itself:
does it call both sinks correctly, does a repository failure never propagate, and is there any
parameter shaped like a secret to misuse in the first place.

The fake structlog logger is installed by monkeypatching the `get_logger` reference
`querymind.security.audit` imports -- not `AuditLogger` itself, and no production code is
changed to make this possible; this is the ordinary way to observe a call to an imported
function without a real logging pipeline configured.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

import pytest

from querymind.security.audit import AuditEventType, AuditLogger

_MAX_USER_AGENT_LENGTH = 300


@dataclass
class _FakeAuditRepository:
    """In-memory stand-in for `AuditRepository` -- records every `create(**fields)` call.
    `raise_on_create`, if set, makes the *next* call raise instead, proving `AuditLogger.record`
    swallows a repository failure rather than propagating it.
    """

    created: list[dict[str, object]] = field(default_factory=list)
    raise_on_create: Exception | None = None

    async def create(self, **fields: object) -> None:
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.created.append(fields)


class _FakeBoundLogger:
    """In-memory stand-in for the `structlog.stdlib.BoundLogger` `AuditLogger` gets from
    `get_logger(...)` -- records every `.info`/`.warning` call for assertions.
    """

    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.warning_calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **fields: object) -> None:
        self.info_calls.append((event, fields))

    def warning(self, event: str, **fields: object) -> None:
        self.warning_calls.append((event, fields))


@pytest.fixture
def fake_repository() -> _FakeAuditRepository:
    return _FakeAuditRepository()


@pytest.fixture
def fake_logger() -> _FakeBoundLogger:
    return _FakeBoundLogger()


@pytest.fixture
def audit_logger(
    monkeypatch: pytest.MonkeyPatch,
    fake_repository: _FakeAuditRepository,
    fake_logger: _FakeBoundLogger,
) -> AuditLogger:
    monkeypatch.setattr("querymind.security.audit.get_logger", lambda **kwargs: fake_logger)
    return AuditLogger(fake_repository)  # type: ignore[arg-type]


class TestRecordSuccess:
    async def test_logs_at_info_level(
        self, audit_logger: AuditLogger, fake_logger: _FakeBoundLogger
    ) -> None:
        await audit_logger.record(
            AuditEventType.LOGIN_SUCCESS, success=True, actor_user_id=1, actor_username="alice"
        )

        assert len(fake_logger.info_calls) == 1
        assert fake_logger.warning_calls == []
        event, fields = fake_logger.info_calls[0]
        assert event == "login_success"
        assert fields["success"] is True
        assert fields["actor_user_id"] == 1
        assert fields["actor_username"] == "alice"

    async def test_persists_via_the_repository(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        await audit_logger.record(
            AuditEventType.REGISTRATION,
            success=True,
            actor_user_id=7,
            actor_username="bob",
            ip_address="127.0.0.1",
            resource="/api/v1/auth/register",
            request_id="req-1",
            correlation_id="corr-1",
        )

        assert len(fake_repository.created) == 1
        record = fake_repository.created[0]
        assert record["event_type"] == "registration"
        assert record["success"] is True
        assert record["actor_user_id"] == 7
        assert record["actor_username"] == "bob"
        assert record["ip_address"] == "127.0.0.1"
        assert record["resource"] == "/api/v1/auth/register"
        assert record["request_id"] == "req-1"
        assert record["correlation_id"] == "corr-1"


class TestRecordFailure:
    async def test_logs_at_warning_level(
        self, audit_logger: AuditLogger, fake_logger: _FakeBoundLogger
    ) -> None:
        await audit_logger.record(
            AuditEventType.LOGIN_FAILURE, success=False, actor_username="mallory"
        )

        assert len(fake_logger.warning_calls) == 1
        assert fake_logger.info_calls == []
        event, fields = fake_logger.warning_calls[0]
        assert event == "login_failure"
        assert fields["success"] is False

    async def test_persists_via_the_repository_too(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        await audit_logger.record(AuditEventType.REFRESH_FAILURE, success=False)

        assert len(fake_repository.created) == 1
        assert fake_repository.created[0]["event_type"] == "refresh_failure"
        assert fake_repository.created[0]["success"] is False


class TestRepositoryFailureIsSwallowed:
    async def test_does_not_raise_and_never_breaks_the_triggering_operation(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        """The whole point of `AuditLogger`'s own docstring: a database hiccup writing an audit
        row must never turn an otherwise-successful login (or any other call site) into a
        failure of its own.
        """
        fake_repository.raise_on_create = RuntimeError("db exploded")

        await audit_logger.record(AuditEventType.LOGIN_SUCCESS, success=True)  # must not raise

    async def test_still_logs_a_warning_about_the_write_failure(
        self,
        audit_logger: AuditLogger,
        fake_repository: _FakeAuditRepository,
        fake_logger: _FakeBoundLogger,
    ) -> None:
        fake_repository.raise_on_create = RuntimeError("db exploded")

        await audit_logger.record(AuditEventType.LOGIN_FAILURE, success=False)

        events = [event for event, _ in fake_logger.warning_calls]
        assert "audit_log_write_failed" in events

    async def test_the_original_event_is_still_logged_before_the_write_is_attempted(
        self,
        audit_logger: AuditLogger,
        fake_repository: _FakeAuditRepository,
        fake_logger: _FakeBoundLogger,
    ) -> None:
        fake_repository.raise_on_create = RuntimeError("db exploded")

        await audit_logger.record(AuditEventType.API_KEY_AUTH_FAILURE, success=False)

        events = [event for event, _ in fake_logger.warning_calls]
        assert "api_key_auth_failure" in events
        assert "audit_log_write_failed" in events


class TestUserAgentTruncation:
    async def test_a_long_user_agent_is_capped_before_persisting(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        await audit_logger.record(
            AuditEventType.API_KEY_AUTH_SUCCESS, success=True, user_agent="A" * 1000
        )

        stored = fake_repository.created[0]["user_agent"]
        assert isinstance(stored, str)
        assert len(stored) == _MAX_USER_AGENT_LENGTH

    async def test_a_short_user_agent_is_stored_unchanged(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        await audit_logger.record(
            AuditEventType.API_KEY_AUTH_SUCCESS, success=True, user_agent="curl/8.0"
        )

        assert fake_repository.created[0]["user_agent"] == "curl/8.0"

    async def test_a_missing_user_agent_stays_none(
        self, audit_logger: AuditLogger, fake_repository: _FakeAuditRepository
    ) -> None:
        await audit_logger.record(
            AuditEventType.API_KEY_AUTH_SUCCESS, success=True, user_agent=None
        )

        assert fake_repository.created[0]["user_agent"] is None


class TestNeverAcceptsASecretShapedField:
    def test_record_has_no_parameter_for_a_password_token_or_api_key(self) -> None:
        """`AuditLogger.record`'s parameter list *is* the entire safety boundary here (see the
        module's own docstring): there is no `password`/`token`/`refresh_token`/`api_key`/
        `authorization`/`secret` parameter to ever misuse. This fails immediately if one is ever
        added, rather than relying on every future call site remembering not to pass one.
        """
        params = set(inspect.signature(AuditLogger.record).parameters)
        forbidden_substrings = ("password", "token", "api_key", "authorization", "secret")

        for param in params:
            for forbidden in forbidden_substrings:
                assert forbidden not in param.lower(), f"{param!r} looks like a secret-shaped field"


class TestNoSecretsInRecordedOutput:
    async def test_a_realistic_login_failure_record_contains_no_secret_shaped_value(
        self,
        audit_logger: AuditLogger,
        fake_repository: _FakeAuditRepository,
        fake_logger: _FakeBoundLogger,
    ) -> None:
        await audit_logger.record(
            AuditEventType.LOGIN_FAILURE,
            success=False,
            actor_username="mallory",
            ip_address="203.0.113.5",
            user_agent="curl/8.0",
            request_id="req-1",
            correlation_id="corr-1",
            resource="/api/v1/auth/login",
            metadata={"error_type": "InvalidCredentialsError"},
        )

        persisted = str(fake_repository.created)
        logged = str(fake_logger.warning_calls)
        for forbidden in ("password", "Bearer ", "refresh_token", ".jwt.", "qm_"):
            assert forbidden not in persisted
            assert forbidden not in logged
