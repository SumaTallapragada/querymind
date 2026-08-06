"""PipelineRunner: performs the exact end-to-end QueryMind sequence.

Every stage is a call into an existing phase's own public entry point --
this module never generates, validates, repairs, formats, retrieves, or
compiles anything itself; see the package docstring for the full
architectural boundary. The orchestrator owns only the *sequence* and
*conditional branching* (whether repair runs, whether execution
succeeded enough to format); each phase still owns its own business
logic entirely.

`run` returns a `QueryMindResponse` directly for two very different
outcomes that both need to be returned, not raised:

1. A full success -- every stage ran, `BusinessAnswer` was produced.
2. A "soft" structured failure a prior phase's own result type already
   expresses without raising -- `SQLExecutionResult.status` not
   `SUCCESS` (rejected/failed/timed out). `ResultFormatterEngine.format`
   only accepts a successful execution, so this is detected and
   converted *before* calling it, rather than letting it raise a generic
   `FormattingError` for an already-well-understood situation.

Anything else -- a stage's own call genuinely raising (a malformed
question, an unreachable database, an exhausted LLM retry policy, ...)
-- is not swallowed here. It propagates as `PipelineExecutionError`,
carrying every stage timing and artifact produced before the failure, so
the caller (`QueryMindEngine.ask`) can still build a complete, honest
`FAILED` response rather than losing that partial progress.

`generate_sql` and `repair_sql` (added in Phase 16, for the FastAPI
service layer's `/query/sql` and `/query/repair` endpoints) share the
"NLU through conditional repair" sequence with `run` via one private
helper, `_generate_and_validate` -- added because those two HTTP
endpoints must stop before execution (one of them must never execute SQL
at all) without either duplicating this sequence inline in a route
(forbidden -- routes must never orchestrate) or running execution
anyway just to discard its result (wasteful, and a real side effect the
caller didn't ask for). `run`'s own observable behavior is unchanged by
this refactor -- see `tests/orchestrator/test_pipeline.py`.

`run` (added in Phase 17, for the streaming service layer's
`POST /query/stream`/`/ws/query` endpoints) also accepts an optional
`event_publisher: StageEventPublisher`, awaited at each stage boundary
this method already tracks for `StageTiming` purposes -- see
`querymind.orchestrator.events` for why this is a structural interface
rather than an import of `querymind.streaming`. `event_publisher` is
`None` for every caller that doesn't pass one (every existing one),
which is a true no-op: no additional work happens, and the returned
`QueryMindResponse` is byte-for-byte identical either way -- see rule 6
of the Phase 17 spec and `tests/orchestrator/test_pipeline.py`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.nlu import QueryParser
from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.exceptions import PipelineConfigurationError, PipelineExecutionError
from querymind.orchestrator.models import (
    GeneratedSqlResult,
    PipelineStage,
    PipelineStatus,
    QueryMindResponse,
    StageTiming,
)
from querymind.orchestrator.statistics import PipelineStatisticsBuilder
from querymind.prompt_compiler import PromptCompiler
from querymind.query_library.models import SQLDialect
from querymind.result_formatter import ResultFormatterEngine
from querymind.retrieval import RetrievalEngine
from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.schema_linker import SchemaLinker
from querymind.sql_execution import ExecutionStatus, SQLExecutionEngine, SQLExecutionResult
from querymind.sql_generation import GeneratedSQL, SQLGenerationEngine
from querymind.sql_repair import RepairStatus, SQLRepairEngine, SQLRepairResult
from querymind.sql_validation import SQLValidationEngine, SQLValidationResult


@dataclass(frozen=True, slots=True)
class _GenerationOutcome:
    """Everything `_generate_and_validate` produced -- private to this module.

    `bundle` is retained (not just the generated SQL) because `repair_sql`
    needs it to call `SQLRepairEngine.repair` directly, without querying
    retrieval a second time.
    """

    bundle: RetrievedKnowledgeBundle
    final_generated_sql: GeneratedSQL
    final_validation_result: SQLValidationResult
    repair_result: SQLRepairResult | None
    repair_attempted: bool
    repair_performed: bool
    stage_timings: tuple[StageTiming, ...]


class PipelineRunner:
    """Runs one question through every QueryMind phase, in order.

    Every collaborator is a fully-constructed instance of that phase's
    own public entry point, constructor-injected -- this class builds
    none of them itself, and none has a "sensible default" the way a
    single phase's own internal collaborators might, since every one of
    these requires real configuration (a database, an LLM provider, a
    metadata registry) only the composition root can supply.
    """

    def __init__(
        self,
        nlu_parser: QueryParser,
        schema_linker: SchemaLinker,
        business_knowledge_registry: BusinessKnowledgeRegistry,
        retrieval_engine: RetrievalEngine,
        prompt_compiler: PromptCompiler,
        sql_generation_engine: SQLGenerationEngine,
        sql_validation_engine: SQLValidationEngine,
        sql_repair_engine: SQLRepairEngine,
        sql_execution_engine: SQLExecutionEngine,
        result_formatter_engine: ResultFormatterEngine,
        statistics_builder: PipelineStatisticsBuilder | None = None,
        dialect: SQLDialect = SQLDialect.POSTGRESQL,
    ) -> None:
        collaborators = {
            "nlu_parser": nlu_parser,
            "schema_linker": schema_linker,
            "business_knowledge_registry": business_knowledge_registry,
            "retrieval_engine": retrieval_engine,
            "prompt_compiler": prompt_compiler,
            "sql_generation_engine": sql_generation_engine,
            "sql_validation_engine": sql_validation_engine,
            "sql_repair_engine": sql_repair_engine,
            "sql_execution_engine": sql_execution_engine,
            "result_formatter_engine": result_formatter_engine,
        }
        missing = [name for name, value in collaborators.items() if value is None]
        if missing:
            raise PipelineConfigurationError(
                f"PipelineRunner requires every collaborator; missing: {', '.join(missing)}."
            )

        self._nlu_parser = nlu_parser
        self._schema_linker = schema_linker
        self._business_knowledge_registry = business_knowledge_registry
        self._retrieval_engine = retrieval_engine
        self._prompt_compiler = prompt_compiler
        self._sql_generation_engine = sql_generation_engine
        self._sql_validation_engine = sql_validation_engine
        self._sql_repair_engine = sql_repair_engine
        self._sql_execution_engine = sql_execution_engine
        self._result_formatter_engine = result_formatter_engine
        self._statistics_builder = statistics_builder or PipelineStatisticsBuilder()
        self._dialect = dialect

    async def run(
        self, question: str, *, event_publisher: StageEventPublisher | None = None
    ) -> QueryMindResponse:
        """Run `question` through the complete pipeline.

        Raises `PipelineExecutionError` if any stage's own call raises.
        Never raises for a "soft" execution failure -- see the module
        docstring. `event_publisher`, if given, is notified at every
        stage boundary and once at the start/end of the whole run -- see
        the module docstring's Phase 17 note; omitting it changes nothing
        about what this method returns or raises.
        """
        pipeline_started = time.perf_counter()
        if event_publisher is not None:
            await event_publisher.pipeline_started(original_question=question)

        outcome = await self._generate_and_validate(question, event_publisher=event_publisher)

        stage_timings = list(outcome.stage_timings)
        current_stage = PipelineStage.SQL_EXECUTION
        execution_result: SQLExecutionResult | None = None
        stage_started = pipeline_started
        try:
            if event_publisher is not None:
                await event_publisher.stage_started(PipelineStage.SQL_EXECUTION)
            stage_started = time.perf_counter()
            execution_result = await self._sql_execution_engine.execute(
                outcome.final_generated_sql, outcome.final_validation_result
            )
            execution_duration_ms = self._elapsed_ms(stage_started)
            stage_timings.append(StageTiming(stage=current_stage, latency_ms=execution_duration_ms))
            if event_publisher is not None:
                await event_publisher.stage_completed(
                    PipelineStage.SQL_EXECUTION, duration_ms=execution_duration_ms
                )

            if execution_result.status is not ExecutionStatus.SUCCESS:
                response = QueryMindResponse(
                    original_question=question,
                    business_answer=None,
                    generated_sql=outcome.final_generated_sql,
                    validation_result=outcome.final_validation_result,
                    repair_result=outcome.repair_result,
                    execution_result=execution_result,
                    statistics=self._statistics_builder.build(
                        total_latency_ms=self._elapsed_ms(pipeline_started),
                        stage_timings=tuple(stage_timings),
                        repair_attempted=outcome.repair_attempted,
                        repair_performed=outcome.repair_performed,
                    ),
                    status=PipelineStatus.FAILED,
                    error=self._execution_error_message(execution_result),
                )
                if event_publisher is not None:
                    await event_publisher.pipeline_completed(response)
                return response

            current_stage = PipelineStage.RESULT_FORMATTING
            if event_publisher is not None:
                await event_publisher.stage_started(PipelineStage.RESULT_FORMATTING)
            stage_started = time.perf_counter()
            business_answer = self._result_formatter_engine.format(execution_result)
            formatting_duration_ms = self._elapsed_ms(stage_started)
            stage_timings.append(
                StageTiming(stage=current_stage, latency_ms=formatting_duration_ms)
            )
            if event_publisher is not None:
                await event_publisher.stage_completed(
                    PipelineStage.RESULT_FORMATTING, duration_ms=formatting_duration_ms
                )

            response = QueryMindResponse(
                original_question=question,
                business_answer=business_answer,
                generated_sql=outcome.final_generated_sql,
                validation_result=outcome.final_validation_result,
                repair_result=outcome.repair_result,
                execution_result=execution_result,
                statistics=self._statistics_builder.build(
                    total_latency_ms=self._elapsed_ms(pipeline_started),
                    stage_timings=tuple(stage_timings),
                    repair_attempted=outcome.repair_attempted,
                    repair_performed=outcome.repair_performed,
                ),
                status=PipelineStatus.SUCCESS,
                error=None,
            )
            if event_publisher is not None:
                await event_publisher.pipeline_completed(response)
            return response
        except Exception as exc:
            if event_publisher is not None:
                failure_duration_ms = self._elapsed_ms(stage_started)
                await event_publisher.stage_failed(
                    current_stage, duration_ms=failure_duration_ms, error=exc
                )
            wrapped = PipelineExecutionError(
                f"Pipeline failed at stage {current_stage.value!r}: {exc}",
                stage=current_stage,
                stage_timings=tuple(stage_timings),
                repair_attempted=outcome.repair_attempted,
                repair_performed=outcome.repair_performed,
                generated_sql=outcome.final_generated_sql,
                validation_result=outcome.final_validation_result,
                repair_result=outcome.repair_result,
                execution_result=execution_result,
            )
            if event_publisher is not None:
                await event_publisher.pipeline_failed(error=wrapped)
            raise wrapped from exc

    async def generate_sql(self, question: str) -> GeneratedSqlResult:
        """Run `question` through NLU, schema linking, retrieval, prompt compilation, SQL
        generation, validation, and conditional repair -- stopping *before* execution and
        result formatting. Powers the `/query/sql` HTTP endpoint, which must never execute SQL.

        Raises `PipelineExecutionError` on the same terms as `run` -- this
        method has no "soft failure" case of its own (there is no
        execution-status to be soft about), so any stage's own exception
        simply propagates.
        """
        pipeline_started = time.perf_counter()
        outcome = await self._generate_and_validate(question)
        return GeneratedSqlResult(
            original_question=question,
            generated_sql=outcome.final_generated_sql,
            validation_result=outcome.final_validation_result,
            repair_result=outcome.repair_result,
            statistics=self._statistics_builder.build(
                total_latency_ms=self._elapsed_ms(pipeline_started),
                stage_timings=outcome.stage_timings,
                repair_attempted=outcome.repair_attempted,
                repair_performed=outcome.repair_performed,
            ),
        )

    async def repair_sql(
        self, question: str, validation_result: SQLValidationResult
    ) -> SQLRepairResult:
        """Repair `validation_result.generated_sql`, rebuilding the retrieval context for
        `question` first (`SQLRepairEngine.repair` requires the same `RetrievedKnowledgeBundle`
        a first-pass generation would have used). Powers the `/query/repair` HTTP endpoint.

        `question` must be the same question that originally produced
        `validation_result` -- retrieval is re-run, not cached, since a
        fresh HTTP request carries no prior pipeline state. Propagates
        whatever the underlying NLU/schema-linking/retrieval/repair calls
        raise; unlike `run`, this is not wrapped in `PipelineExecutionError`
        -- there is no larger pipeline run for a partial-progress
        exception to usefully describe here.
        """
        query_context = self._nlu_parser.parse(question)
        linked_context = self._schema_linker.link(query_context)
        self._business_knowledge_registry.load()
        bundle = self._retrieval_engine.retrieve(linked_context)
        return self._sql_repair_engine.repair(
            validation_result.generated_sql, validation_result, bundle
        )

    async def _generate_and_validate(
        self, question: str, *, event_publisher: StageEventPublisher | None = None
    ) -> _GenerationOutcome:
        """NLU through conditional repair -- the sequence `run`, `generate_sql`, and (partly,
        for retrieval) `repair_sql` all share. Raises `PipelineExecutionError` exactly as `run`
        did before this method existed; see that method's docstring for the exact contract.
        `event_publisher` is notified at each stage boundary below -- see `run`'s own docstring.
        """
        stage_timings: list[StageTiming] = []
        current_stage = PipelineStage.NLU
        repair_attempted = False
        repair_performed = False
        generated_sql = None
        validation_result = None
        repair_result = None
        stage_started = time.perf_counter()

        try:
            await self._notify_started(event_publisher, PipelineStage.NLU)
            stage_started = time.perf_counter()
            query_context = self._nlu_parser.parse(question)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.NLU, stage_started
            )

            current_stage = PipelineStage.SCHEMA_LINKING
            await self._notify_started(event_publisher, PipelineStage.SCHEMA_LINKING)
            stage_started = time.perf_counter()
            linked_context = self._schema_linker.link(query_context)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.SCHEMA_LINKING, stage_started
            )

            current_stage = PipelineStage.BUSINESS_KNOWLEDGE
            await self._notify_started(event_publisher, PipelineStage.BUSINESS_KNOWLEDGE)
            stage_started = time.perf_counter()
            self._business_knowledge_registry.load()
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.BUSINESS_KNOWLEDGE, stage_started
            )

            current_stage = PipelineStage.RETRIEVAL
            await self._notify_started(event_publisher, PipelineStage.RETRIEVAL)
            stage_started = time.perf_counter()
            bundle = self._retrieval_engine.retrieve(linked_context)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.RETRIEVAL, stage_started
            )

            current_stage = PipelineStage.PROMPT_COMPILATION
            await self._notify_started(event_publisher, PipelineStage.PROMPT_COMPILATION)
            stage_started = time.perf_counter()
            compiled_prompt = self._prompt_compiler.compile(bundle, dialect=self._dialect)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.PROMPT_COMPILATION, stage_started
            )

            current_stage = PipelineStage.SQL_GENERATION
            await self._notify_started(event_publisher, PipelineStage.SQL_GENERATION)
            stage_started = time.perf_counter()
            generated_sql = self._sql_generation_engine.generate(compiled_prompt)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.SQL_GENERATION, stage_started
            )
            # The LLM call itself already happened inside SQL_GENERATION (SQLGenerationEngine
            # wraps LLMAdapter internally) -- its own, independently measured latency is
            # carried on GeneratedSQL.llm_metrics, so LLM gets its own StageTiming without
            # this orchestrator calling LLMAdapter a second time.
            llm_duration_ms = generated_sql.llm_metrics.latency_ms
            stage_timings.append(StageTiming(stage=PipelineStage.LLM, latency_ms=llm_duration_ms))
            if event_publisher is not None:
                await event_publisher.stage_started(PipelineStage.LLM)
                await event_publisher.stage_completed(
                    PipelineStage.LLM, duration_ms=llm_duration_ms
                )

            current_stage = PipelineStage.SQL_VALIDATION
            await self._notify_started(event_publisher, PipelineStage.SQL_VALIDATION)
            stage_started = time.perf_counter()
            validation_result = self._sql_validation_engine.validate(generated_sql)
            await self._notify_completed(
                event_publisher, stage_timings, PipelineStage.SQL_VALIDATION, stage_started
            )

            final_generated_sql = generated_sql
            final_validation_result = validation_result
            repair_attempted = not validation_result.is_valid
            if repair_attempted:
                current_stage = PipelineStage.SQL_REPAIR
                await self._notify_started(event_publisher, PipelineStage.SQL_REPAIR)
                stage_started = time.perf_counter()
                repair_result = self._sql_repair_engine.repair(
                    generated_sql, validation_result, bundle
                )
                await self._notify_completed(
                    event_publisher, stage_timings, PipelineStage.SQL_REPAIR, stage_started
                )
                repair_performed = repair_result.status is RepairStatus.REPAIRED
                # Reuse the repair engine's own validation output -- never re-validate manually.
                final_generated_sql = repair_result.final_sql
                final_validation_result = repair_result.final_validation_result

            return _GenerationOutcome(
                bundle=bundle,
                final_generated_sql=final_generated_sql,
                final_validation_result=final_validation_result,
                repair_result=repair_result,
                repair_attempted=repair_attempted,
                repair_performed=repair_performed,
                stage_timings=tuple(stage_timings),
            )
        except Exception as exc:
            if event_publisher is not None:
                await event_publisher.stage_failed(
                    current_stage, duration_ms=self._elapsed_ms(stage_started), error=exc
                )
            wrapped = PipelineExecutionError(
                f"Pipeline failed at stage {current_stage.value!r}: {exc}",
                stage=current_stage,
                stage_timings=tuple(stage_timings),
                repair_attempted=repair_attempted,
                repair_performed=repair_performed,
                generated_sql=generated_sql,
                validation_result=validation_result,
                repair_result=repair_result,
                execution_result=None,
            )
            if event_publisher is not None:
                await event_publisher.pipeline_failed(error=wrapped)
            raise wrapped from exc

    @staticmethod
    async def _notify_started(publisher: StageEventPublisher | None, stage: PipelineStage) -> None:
        if publisher is not None:
            await publisher.stage_started(stage)

    @staticmethod
    async def _notify_completed(
        publisher: StageEventPublisher | None,
        stage_timings: list[StageTiming],
        stage: PipelineStage,
        started: float,
    ) -> None:
        """Append `stage`'s `StageTiming` (identical to the pre-Phase-17 `_timing` helper) and,
        if `publisher` is given, notify it with that exact same duration -- one measurement,
        never two independent clock reads for what must be the same number.
        """
        duration_ms = PipelineRunner._elapsed_ms(started)
        stage_timings.append(StageTiming(stage=stage, latency_ms=duration_ms))
        if publisher is not None:
            await publisher.stage_completed(stage, duration_ms=duration_ms)

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000

    @staticmethod
    def _execution_error_message(execution_result: SQLExecutionResult) -> str:
        if execution_result.execution_error is not None:
            return execution_result.execution_error.message
        return f"SQL execution did not succeed (status={execution_result.status.value})."
