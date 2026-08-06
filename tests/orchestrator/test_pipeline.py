"""Tests for `querymind.orchestrator.pipeline.PipelineRunner` — sequencing and branching only.

Every collaborator is a small scripted fake returning a real, minimally
built model instance (via `conftest.py`'s synthetic builders) -- this
file verifies `PipelineRunner`'s own control flow (the exact sequence,
the conditional repair branch, the "soft" execution-failure short
circuit, exception-to-`PipelineExecutionError` conversion), never any
individual phase's own algorithm; that is each phase's own test suite's
job. The real, fully-wired stack is exercised in `test_integration.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from querymind.orchestrator.exceptions import PipelineConfigurationError, PipelineExecutionError
from querymind.orchestrator.models import PipelineStage, PipelineStatus
from querymind.orchestrator.pipeline import PipelineRunner
from querymind.sql_execution.models import ExecutionError, ExecutionStatus
from querymind.sql_repair.models import RepairStatus

from .conftest import (
    make_bundle,
    make_business_answer,
    make_compiled_prompt,
    make_execution_result,
    make_generated_sql,
    make_issue,
    make_linked_context,
    make_query_context,
    make_repair_result,
    make_validation_result,
)


def _resolve(outcome: Any) -> Any:
    if isinstance(outcome, Exception):
        raise outcome
    return outcome


class _FakeNLUParser:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def parse(self, question: str) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeSchemaLinker:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def link(self, query_context: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeBusinessKnowledgeRegistry:
    def __init__(self, outcome: Exception | None = None) -> None:
        self._outcome = outcome
        self.calls = 0

    def load(self) -> Any:
        self.calls += 1
        if self._outcome is not None:
            raise self._outcome
        return None


class _FakeRetrievalEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def retrieve(self, linked_query_context: Any, top_k: int | None = None) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakePromptCompiler:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def compile(self, bundle: Any, dialect: Any = None) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeSQLGenerationEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def generate(self, compiled_prompt: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeSQLValidationEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def validate(self, generated_sql: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeSQLRepairEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def repair(self, generated_sql: Any, validation_result: Any, bundle: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeSQLExecutionEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    async def execute(self, generated_sql: Any, validation_result: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


class _FakeResultFormatterEngine:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def format(self, execution_result: Any) -> Any:
        self.calls += 1
        return _resolve(self._outcome)


_QUESTION = "Who are our top customers by revenue?"
_QUERY_CONTEXT = make_query_context()
_LINKED_CONTEXT = make_linked_context()
_BUNDLE = make_bundle()
_COMPILED_PROMPT = make_compiled_prompt()
_GENERATED_SQL = make_generated_sql("SELECT customer_id FROM customers;")
_VALID_RESULT = make_validation_result(_GENERATED_SQL)
_INVALID_RESULT = make_validation_result(_GENERATED_SQL, errors=(make_issue("unknown_table"),))
_EXECUTION_RESULT = make_execution_result(_GENERATED_SQL)
_BUSINESS_ANSWER = make_business_answer(_EXECUTION_RESULT)


def _build_runner(
    *,
    nlu: Any = None,
    schema_linker: Any = None,
    business_knowledge: Any = None,
    retrieval: Any = None,
    prompt_compiler: Any = None,
    sql_generation: Any = None,
    sql_validation: Any = None,
    sql_repair: Any = None,
    sql_execution: Any = None,
    result_formatter: Any = None,
) -> tuple[PipelineRunner, dict[str, Any]]:
    fakes = {
        "nlu": nlu or _FakeNLUParser(_QUERY_CONTEXT),
        "schema_linker": schema_linker or _FakeSchemaLinker(_LINKED_CONTEXT),
        "business_knowledge": business_knowledge or _FakeBusinessKnowledgeRegistry(),
        "retrieval": retrieval or _FakeRetrievalEngine(_BUNDLE),
        "prompt_compiler": prompt_compiler or _FakePromptCompiler(_COMPILED_PROMPT),
        "sql_generation": sql_generation or _FakeSQLGenerationEngine(_GENERATED_SQL),
        "sql_validation": sql_validation or _FakeSQLValidationEngine(_VALID_RESULT),
        "sql_repair": sql_repair or _FakeSQLRepairEngine(None),
        "sql_execution": sql_execution or _FakeSQLExecutionEngine(_EXECUTION_RESULT),
        "result_formatter": result_formatter or _FakeResultFormatterEngine(_BUSINESS_ANSWER),
    }
    runner = PipelineRunner(
        nlu_parser=fakes["nlu"],  # type: ignore[arg-type]
        schema_linker=fakes["schema_linker"],  # type: ignore[arg-type]
        business_knowledge_registry=fakes["business_knowledge"],  # type: ignore[arg-type]
        retrieval_engine=fakes["retrieval"],  # type: ignore[arg-type]
        prompt_compiler=fakes["prompt_compiler"],  # type: ignore[arg-type]
        sql_generation_engine=fakes["sql_generation"],  # type: ignore[arg-type]
        sql_validation_engine=fakes["sql_validation"],  # type: ignore[arg-type]
        sql_repair_engine=fakes["sql_repair"],  # type: ignore[arg-type]
        sql_execution_engine=fakes["sql_execution"],  # type: ignore[arg-type]
        result_formatter_engine=fakes["result_formatter"],  # type: ignore[arg-type]
    )
    return runner, fakes


class TestSuccessfulPipeline:
    async def test_every_stage_runs_in_order_and_produces_success(self) -> None:
        runner, fakes = _build_runner()
        response = await runner.run(_QUESTION)

        assert response.status is PipelineStatus.SUCCESS
        assert response.error is None
        assert response.business_answer is _BUSINESS_ANSWER
        assert response.generated_sql is _GENERATED_SQL
        assert response.validation_result is _VALID_RESULT
        assert response.repair_result is None
        assert response.execution_result is _EXECUTION_RESULT
        assert response.original_question == _QUESTION

    async def test_repair_is_skipped_for_valid_sql(self) -> None:
        runner, fakes = _build_runner()
        await runner.run(_QUESTION)
        assert fakes["sql_repair"].calls == 0

    async def test_statistics_report_repair_not_attempted(self) -> None:
        runner, _ = _build_runner()
        response = await runner.run(_QUESTION)
        assert response.statistics.repair_attempted is False
        assert response.statistics.repair_performed is False

    async def test_every_stage_except_repair_has_a_timing(self) -> None:
        runner, _ = _build_runner()
        response = await runner.run(_QUESTION)
        stages = {timing.stage for timing in response.statistics.stage_timings}
        assert stages == set(PipelineStage) - {PipelineStage.SQL_REPAIR}

    async def test_llm_stage_timing_comes_from_generated_sqls_own_metrics(self) -> None:
        runner, _ = _build_runner()
        response = await runner.run(_QUESTION)
        llm_timing = next(
            t for t in response.statistics.stage_timings if t.stage is PipelineStage.LLM
        )
        assert llm_timing.latency_ms == _GENERATED_SQL.llm_metrics.latency_ms

    async def test_total_latency_is_measured(self) -> None:
        runner, _ = _build_runner()
        response = await runner.run(_QUESTION)
        assert response.statistics.total_latency_ms >= 0.0


class TestRepairPath:
    async def test_repair_runs_when_validation_fails(self) -> None:
        repaired = make_generated_sql("SELECT customer_id FROM customers WHERE true;")
        repaired_validation = make_validation_result(repaired)
        repair_result = make_repair_result(_GENERATED_SQL, repaired, repaired_validation)

        runner, fakes = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(repair_result),
        )
        response = await runner.run(_QUESTION)

        assert fakes["sql_repair"].calls == 1
        assert response.statistics.repair_attempted is True
        assert response.statistics.repair_performed is True
        assert response.repair_result is repair_result
        # The SQL ultimately executed/reported must be the repaired SQL, not the original.
        assert response.generated_sql is repaired
        assert response.validation_result is repaired_validation
        assert response.status is PipelineStatus.SUCCESS

    async def test_repair_that_does_not_fully_succeed_is_still_reported(self) -> None:
        repair_result = make_repair_result(
            _GENERATED_SQL,
            _GENERATED_SQL,
            _INVALID_RESULT,
            status=RepairStatus.MAX_ATTEMPTS_REACHED,
        )
        runner, _ = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(repair_result),
            sql_execution=_FakeSQLExecutionEngine(
                make_execution_result(
                    _GENERATED_SQL,
                    status=ExecutionStatus.REJECTED,
                    error=ExecutionError(code="execution_rejected", message="still invalid"),
                )
            ),
        )
        response = await runner.run(_QUESTION)

        assert response.statistics.repair_attempted is True
        assert response.statistics.repair_performed is False
        assert response.status is PipelineStatus.FAILED
        assert response.business_answer is None

    async def test_repair_stage_has_its_own_timing(self) -> None:
        repair_result = make_repair_result(_GENERATED_SQL, _GENERATED_SQL, _VALID_RESULT)
        runner, _ = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(repair_result),
        )
        response = await runner.run(_QUESTION)
        stages = {timing.stage for timing in response.statistics.stage_timings}
        assert PipelineStage.SQL_REPAIR in stages


class TestSoftExecutionFailure:
    async def test_a_failed_execution_short_circuits_before_result_formatting(self) -> None:
        failed_execution = make_execution_result(
            _GENERATED_SQL,
            status=ExecutionStatus.FAILED,
            error=ExecutionError(code="execution_failed", message="relation does not exist"),
        )
        runner, fakes = _build_runner(sql_execution=_FakeSQLExecutionEngine(failed_execution))
        response = await runner.run(_QUESTION)

        assert fakes["result_formatter"].calls == 0
        assert response.status is PipelineStatus.FAILED
        assert response.business_answer is None
        assert response.execution_result is failed_execution
        assert response.error == "relation does not exist"

    async def test_execution_stage_still_gets_a_timing_on_soft_failure(self) -> None:
        failed_execution = make_execution_result(_GENERATED_SQL, status=ExecutionStatus.TIMEOUT)
        runner, _ = _build_runner(sql_execution=_FakeSQLExecutionEngine(failed_execution))
        response = await runner.run(_QUESTION)
        stages = {timing.stage for timing in response.statistics.stage_timings}
        assert PipelineStage.SQL_EXECUTION in stages
        assert PipelineStage.RESULT_FORMATTING not in stages


class TestStageExceptionPropagation:
    async def test_an_nlu_failure_raises_pipeline_execution_error_with_no_partial_artifacts(
        self,
    ) -> None:
        runner, _ = _build_runner(nlu=_FakeNLUParser(ValueError("empty question")))
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.run(_QUESTION)

        error = exc_info.value
        assert error.stage is PipelineStage.NLU
        assert error.stage_timings == ()
        assert error.generated_sql is None
        assert error.execution_result is None

    async def test_an_llm_sql_generation_failure_carries_every_prior_stages_timing(self) -> None:
        runner, _ = _build_runner(
            sql_generation=_FakeSQLGenerationEngine(RuntimeError("LLM retry exhausted"))
        )
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.run(_QUESTION)

        error = exc_info.value
        assert error.stage is PipelineStage.SQL_GENERATION
        stages = {timing.stage for timing in error.stage_timings}
        assert stages == {
            PipelineStage.NLU,
            PipelineStage.SCHEMA_LINKING,
            PipelineStage.BUSINESS_KNOWLEDGE,
            PipelineStage.RETRIEVAL,
            PipelineStage.PROMPT_COMPILATION,
        }
        assert error.generated_sql is None
        assert "LLM retry exhausted" in str(error)

    async def test_a_repair_failure_carries_the_original_generated_sql_and_validation(self) -> None:
        runner, _ = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(RuntimeError("repair LLM call failed")),
        )
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.run(_QUESTION)

        error = exc_info.value
        assert error.stage is PipelineStage.SQL_REPAIR
        assert error.generated_sql is _GENERATED_SQL
        assert error.validation_result is _INVALID_RESULT
        assert error.repair_result is None
        assert error.repair_attempted is True

    async def test_a_schema_linking_failure_stops_before_retrieval(self) -> None:
        runner, fakes = _build_runner(
            schema_linker=_FakeSchemaLinker(RuntimeError("registry empty"))
        )
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.run(_QUESTION)

        assert exc_info.value.stage is PipelineStage.SCHEMA_LINKING
        assert fakes["retrieval"].calls == 0


class _RecordingEventPublisher:
    """A `StageEventPublisher` that just records every call it received, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def pipeline_started(self, *, original_question: str) -> None:
        self.calls.append(("pipeline_started", original_question))

    async def stage_started(self, stage: PipelineStage) -> None:
        self.calls.append(("stage_started", stage))

    async def stage_completed(self, stage: PipelineStage, *, duration_ms: float) -> None:
        self.calls.append(("stage_completed", stage, duration_ms))

    async def stage_failed(
        self, stage: PipelineStage, *, duration_ms: float, error: BaseException
    ) -> None:
        self.calls.append(("stage_failed", stage, duration_ms, error))

    async def pipeline_completed(self, response: Any) -> None:
        self.calls.append(("pipeline_completed", response))

    async def pipeline_failed(self, *, error: BaseException) -> None:
        self.calls.append(("pipeline_failed", error))


class TestEventPublisher:
    async def test_omitting_the_publisher_changes_nothing(self) -> None:
        runner, _ = _build_runner()
        response = await runner.run(_QUESTION)
        assert response.status is PipelineStatus.SUCCESS

    async def test_a_successful_run_reports_pipeline_started_and_completed(self) -> None:
        runner, _ = _build_runner()
        publisher = _RecordingEventPublisher()
        response = await runner.run(_QUESTION, event_publisher=publisher)

        assert publisher.calls[0] == ("pipeline_started", _QUESTION)
        assert publisher.calls[-1] == ("pipeline_completed", response)

    async def test_every_stage_gets_a_matched_started_completed_pair(self) -> None:
        runner, _ = _build_runner()
        publisher = _RecordingEventPublisher()
        await runner.run(_QUESTION, event_publisher=publisher)

        started = [stage for event, stage, *_ in publisher.calls if event == "stage_started"]
        completed = [stage for event, stage, *_ in publisher.calls if event == "stage_completed"]
        assert set(started) == set(PipelineStage) - {PipelineStage.SQL_REPAIR}
        assert started == completed

    async def test_stage_events_are_emitted_in_pipeline_order(self) -> None:
        runner, _ = _build_runner()
        publisher = _RecordingEventPublisher()
        await runner.run(_QUESTION, event_publisher=publisher)

        started_in_order = [
            stage for event, stage, *_ in publisher.calls if event == "stage_started"
        ]
        # LLM is a synthetic stage timed from `GeneratedSQL.llm_metrics` (the LLM call already
        # happened inside SQL_GENERATION) -- its event fires right after SQL_GENERATION's own,
        # not at the position `PipelineStage`'s declaration order would suggest.
        assert started_in_order == [
            PipelineStage.NLU,
            PipelineStage.SCHEMA_LINKING,
            PipelineStage.BUSINESS_KNOWLEDGE,
            PipelineStage.RETRIEVAL,
            PipelineStage.PROMPT_COMPILATION,
            PipelineStage.SQL_GENERATION,
            PipelineStage.LLM,
            PipelineStage.SQL_VALIDATION,
            PipelineStage.SQL_EXECUTION,
            PipelineStage.RESULT_FORMATTING,
        ]

    async def test_repair_running_emits_its_own_started_completed_pair(self) -> None:
        repair_result = make_repair_result(_GENERATED_SQL, _GENERATED_SQL, _VALID_RESULT)
        runner, _ = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(repair_result),
        )
        publisher = _RecordingEventPublisher()
        await runner.run(_QUESTION, event_publisher=publisher)

        started = {stage for event, stage, *_ in publisher.calls if event == "stage_started"}
        assert PipelineStage.SQL_REPAIR in started

    async def test_a_soft_execution_failure_still_reports_pipeline_completed(self) -> None:
        failed_execution = make_execution_result(_GENERATED_SQL, status=ExecutionStatus.TIMEOUT)
        runner, _ = _build_runner(sql_execution=_FakeSQLExecutionEngine(failed_execution))
        publisher = _RecordingEventPublisher()
        response = await runner.run(_QUESTION, event_publisher=publisher)

        assert response.status is PipelineStatus.FAILED
        assert publisher.calls[-1] == ("pipeline_completed", response)
        assert not any(event == "pipeline_failed" for event, *_ in publisher.calls)

    async def test_a_stage_exception_reports_stage_failed_then_pipeline_failed(self) -> None:
        runner, _ = _build_runner(
            sql_generation=_FakeSQLGenerationEngine(RuntimeError("LLM retry exhausted"))
        )
        publisher = _RecordingEventPublisher()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.run(_QUESTION, event_publisher=publisher)

        failed_event = publisher.calls[-2]
        assert failed_event[0] == "stage_failed"
        assert failed_event[1] is PipelineStage.SQL_GENERATION
        assert failed_event[3] is exc_info.value.__cause__
        assert publisher.calls[-1] == ("pipeline_failed", exc_info.value)

    async def test_a_soft_execution_failure_never_emits_result_formatting_events(self) -> None:
        failed_execution = make_execution_result(_GENERATED_SQL, status=ExecutionStatus.FAILED)
        runner, _ = _build_runner(sql_execution=_FakeSQLExecutionEngine(failed_execution))
        publisher = _RecordingEventPublisher()
        await runner.run(_QUESTION, event_publisher=publisher)

        stages_seen = {stage for event, stage, *_ in publisher.calls if "stage_" in event}
        assert PipelineStage.RESULT_FORMATTING not in stages_seen


class TestConfiguration:
    def test_missing_a_required_collaborator_raises_pipeline_configuration_error(self) -> None:
        with pytest.raises(PipelineConfigurationError):
            PipelineRunner(
                nlu_parser=None,  # type: ignore[arg-type]
                schema_linker=_FakeSchemaLinker(_LINKED_CONTEXT),  # type: ignore[arg-type]
                business_knowledge_registry=_FakeBusinessKnowledgeRegistry(),  # type: ignore[arg-type]
                retrieval_engine=_FakeRetrievalEngine(_BUNDLE),  # type: ignore[arg-type]
                prompt_compiler=_FakePromptCompiler(_COMPILED_PROMPT),  # type: ignore[arg-type]
                sql_generation_engine=_FakeSQLGenerationEngine(_GENERATED_SQL),  # type: ignore[arg-type]
                sql_validation_engine=_FakeSQLValidationEngine(_VALID_RESULT),  # type: ignore[arg-type]
                sql_repair_engine=_FakeSQLRepairEngine(None),  # type: ignore[arg-type]
                sql_execution_engine=_FakeSQLExecutionEngine(_EXECUTION_RESULT),  # type: ignore[arg-type]
                result_formatter_engine=_FakeResultFormatterEngine(_BUSINESS_ANSWER),  # type: ignore[arg-type]
            )


class TestGenerateSql:
    async def test_a_valid_question_never_touches_execution_or_formatting(self) -> None:
        runner, fakes = _build_runner()
        result = await runner.generate_sql(_QUESTION)

        assert result.generated_sql is _GENERATED_SQL
        assert result.validation_result is _VALID_RESULT
        assert result.repair_result is None
        assert fakes["sql_execution"].calls == 0
        assert fakes["result_formatter"].calls == 0

    async def test_repair_runs_and_the_repaired_sql_is_returned(self) -> None:
        repaired = make_generated_sql("SELECT customer_id FROM customers WHERE true;")
        repaired_validation = make_validation_result(repaired)
        repair_result = make_repair_result(_GENERATED_SQL, repaired, repaired_validation)

        runner, fakes = _build_runner(
            sql_validation=_FakeSQLValidationEngine(_INVALID_RESULT),
            sql_repair=_FakeSQLRepairEngine(repair_result),
        )
        result = await runner.generate_sql(_QUESTION)

        assert fakes["sql_repair"].calls == 1
        assert result.generated_sql is repaired
        assert result.repair_result is repair_result
        assert result.statistics.repair_attempted is True

    async def test_stage_failure_raises_pipeline_execution_error(self) -> None:
        runner, _ = _build_runner(nlu=_FakeNLUParser(ValueError("bad question")))
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.generate_sql(_QUESTION)
        assert exc_info.value.stage is PipelineStage.NLU

    async def test_statistics_have_no_execution_or_formatting_timing(self) -> None:
        runner, _ = _build_runner()
        result = await runner.generate_sql(_QUESTION)
        stages = {t.stage for t in result.statistics.stage_timings}
        assert PipelineStage.SQL_EXECUTION not in stages
        assert PipelineStage.RESULT_FORMATTING not in stages


class TestRepairSql:
    async def test_rebuilds_retrieval_context_and_calls_repair(self) -> None:
        repair_result = make_repair_result(_GENERATED_SQL, _GENERATED_SQL, _VALID_RESULT)
        runner, fakes = _build_runner(sql_repair=_FakeSQLRepairEngine(repair_result))

        result = await runner.repair_sql(_QUESTION, _INVALID_RESULT)

        assert fakes["nlu"].calls == 1
        assert fakes["schema_linker"].calls == 1
        assert fakes["retrieval"].calls == 1
        assert fakes["sql_repair"].calls == 1
        assert result is repair_result

    async def test_never_calls_sql_generation_validation_or_execution(self) -> None:
        repair_result = make_repair_result(_GENERATED_SQL, _GENERATED_SQL, _VALID_RESULT)
        runner, fakes = _build_runner(sql_repair=_FakeSQLRepairEngine(repair_result))

        await runner.repair_sql(_QUESTION, _INVALID_RESULT)

        assert fakes["sql_generation"].calls == 0
        assert fakes["sql_validation"].calls == 0
        assert fakes["sql_execution"].calls == 0

    async def test_repairs_the_generated_sql_embedded_in_the_validation_result(self) -> None:
        repair_result = make_repair_result(_GENERATED_SQL, _GENERATED_SQL, _VALID_RESULT)
        runner, fakes = _build_runner(sql_repair=_FakeSQLRepairEngine(repair_result))

        await runner.repair_sql(_QUESTION, _INVALID_RESULT)

        assert fakes["sql_repair"].calls == 1

    async def test_a_retrieval_failure_propagates(self) -> None:
        runner, _ = _build_runner(retrieval=_FakeRetrievalEngine(RuntimeError("retrieval down")))
        with pytest.raises(RuntimeError, match="retrieval down"):
            await runner.repair_sql(_QUESTION, _INVALID_RESULT)
