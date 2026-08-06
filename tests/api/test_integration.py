"""End-to-end tests against the real, fully wired FastAPI app.

Every engine behind the HTTP layer is real -- the real `ApplicationContainer`,
the real metadata/business knowledge/query library registries, the real
`SchemaLinker`/`RetrievalEngine`/`PromptCompiler`/`SQLValidationEngine`/
`SQLRepairEngine`/`SQLExecutionEngine`, and a real `LLMAdapter`/`ClaudeProvider`
whose network is replaced by `httpx.MockTransport` -- against the real,
already-running, seeded local Postgres instance. Mirrors
`tests/orchestrator/test_integration.py`'s own precedent and reuses its
exact `_VALID_SQL`/`_BROKEN_SQL` (both already proven to validate/fail
against the real schema).
"""

from __future__ import annotations

from querymind.core.config import Settings
from querymind.query_library.models import SQLDialect
from querymind.sql_validation.models import SQLValidationResult
from tests.api.conftest import integration_client, sql_handler

_QUESTION = "Who are our top 10 customers by revenue?"

_VALID_SQL = (
    "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
    "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
    "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
)

_BROKEN_SQL = (
    "SELECT c.customer_id, w.warehouse_id "
    "FROM customers c JOIN warehouses w ON w.warehouse_id = c.customer_id;"
)


async def test_post_query_answers_a_real_question_end_to_end(real_settings: Settings) -> None:
    async with integration_client(real_settings, sql_handler([_VALID_SQL])) as client:
        response = await client.post("/api/v1/query", json={"question": _QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["generated_sql"]["sql"] == _VALID_SQL
    assert body["business_answer"] is not None
    assert body["execution_result"]["status"] == "success"


async def test_post_query_repairs_a_hallucinated_join_transparently(
    real_settings: Settings,
) -> None:
    async with integration_client(real_settings, sql_handler([_BROKEN_SQL, _VALID_SQL])) as client:
        response = await client.post("/api/v1/query", json={"question": _QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["statistics"]["repair_attempted"] is True
    assert body["statistics"]["repair_performed"] is True
    assert body["repair_result"]["status"] == "repaired"
    assert body["generated_sql"]["sql"] == _VALID_SQL


async def test_post_query_sql_never_touches_the_database(real_settings: Settings) -> None:
    async with integration_client(real_settings, sql_handler([_VALID_SQL])) as client:
        response = await client.post("/api/v1/query/sql", json={"question": _QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["generated_sql"]["sql"] == _VALID_SQL
    assert body["validation_result"]["is_valid"] is True
    assert body["repair_result"] is None


async def test_full_pipeline_matches_sql_generated_via_query_sql(real_settings: Settings) -> None:
    async with integration_client(real_settings, sql_handler([_VALID_SQL, _VALID_SQL])) as client:
        preview_response = await client.post("/api/v1/query/sql", json={"question": _QUESTION})
        assert preview_response.status_code == 200
        validation_result = SQLValidationResult.model_validate(
            preview_response.json()["validation_result"]
        )

        execute_response = await client.post(
            "/api/v1/query/execute",
            json={"validation_result": validation_result.model_dump(mode="json")},
        )

    assert execute_response.status_code == 200
    execute_body = execute_response.json()
    assert execute_body["status"] == "success"
    assert execute_body["query_result"] is not None


async def test_query_validate_reports_a_real_hallucinated_join_as_invalid(
    real_settings: Settings,
) -> None:
    async with integration_client(real_settings, sql_handler([_VALID_SQL])) as client:
        response = await client.post(
            "/api/v1/query/validate",
            json={"sql": _BROKEN_SQL, "dialect": SQLDialect.POSTGRESQL.value},
        )

    assert response.status_code == 200
    assert response.json()["is_valid"] is False


async def test_query_repair_fixes_a_real_hallucinated_join_given_only_the_question(
    real_settings: Settings,
) -> None:
    async with integration_client(real_settings, sql_handler([_VALID_SQL])) as client:
        validate_response = await client.post(
            "/api/v1/query/validate",
            json={"sql": _BROKEN_SQL, "dialect": SQLDialect.POSTGRESQL.value},
        )
        assert validate_response.json()["is_valid"] is False

        repair_response = await client.post(
            "/api/v1/query/repair",
            json={"question": _QUESTION, "validation_result": validate_response.json()},
        )

    assert repair_response.status_code == 200
    body = repair_response.json()
    assert body["status"] == "repaired"
    assert body["final_sql"]["sql"] == _VALID_SQL
