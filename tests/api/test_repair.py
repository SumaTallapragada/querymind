"""Unit tests for `POST /api/v1/query/repair`. `QueryMindEngineDep` is mocked -- verifies the
route passes both the question and the validation result through to
`QueryMindEngine.repair` unchanged, and returns whatever `SQLRepairResult` it produces
regardless of whether repair actually succeeded.

Requires at least `ANALYST` (Phase 22B) -- `_authenticated_as_analyst` below overrides
`get_current_user` for every test in this file; see `test_diagnostics.py`'s identical fixture
for why.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user, get_query_mind_engine
from querymind.auth.models import UserRole
from querymind.sql_repair.models import RepairStatus, SQLRepairResult
from querymind.sql_validation.models import SQLValidationResult
from tests.api.conftest import make_user_read
from tests.orchestrator.conftest import (
    make_generated_sql,
    make_issue,
    make_repair_result,
    make_validation_result,
)

_QUESTION = "Who are our top 5 customers by revenue?"
_BROKEN_SQL = "SELECT c.customer_id FROM customers c JOIN nonexistent n ON n.id = c.customer_id;"


@pytest.fixture(autouse=True)
def _authenticated_as_analyst(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)


class _FakeEngine:
    def __init__(self, result: SQLRepairResult) -> None:
        self._result = result
        self.calls: list[tuple[str, SQLValidationResult]] = []

    async def repair(
        self, question: str, validation_result: SQLValidationResult
    ) -> SQLRepairResult:
        self.calls.append((question, validation_result))
        return self._result


def _broken_validation_result() -> SQLValidationResult:
    generated_sql = make_generated_sql(_BROKEN_SQL)
    return make_validation_result(generated_sql, errors=(make_issue("unknown_table"),))


async def test_passes_question_and_validation_result_through_to_repair(
    app: FastAPI, client: AsyncClient
) -> None:
    validation_result = _broken_validation_result()
    fixed_sql = make_generated_sql("SELECT c.customer_id FROM customers c;")
    fixed_validation = make_validation_result(fixed_sql)
    result = make_repair_result(validation_result.generated_sql, fixed_sql, fixed_validation)
    fake = _FakeEngine(result)
    app.dependency_overrides[get_query_mind_engine] = lambda: fake

    response = await client.post(
        "/api/v1/query/repair",
        json={
            "question": _QUESTION,
            "validation_result": validation_result.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "repaired"
    assert len(fake.calls) == 1
    called_question, called_validation_result = fake.calls[0]
    assert called_question == _QUESTION
    assert called_validation_result.generated_sql.sql == _BROKEN_SQL


async def test_an_unrepairable_result_still_returns_200(app: FastAPI, client: AsyncClient) -> None:
    validation_result = _broken_validation_result()
    result = make_repair_result(
        validation_result.generated_sql,
        validation_result.generated_sql,
        validation_result,
        status=RepairStatus.UNREPAIRABLE,
    )
    app.dependency_overrides[get_query_mind_engine] = lambda: _FakeEngine(result)

    response = await client.post(
        "/api/v1/query/repair",
        json={
            "question": _QUESTION,
            "validation_result": validation_result.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unrepairable"
