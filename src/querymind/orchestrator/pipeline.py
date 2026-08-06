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
"""

from __future__ import annotations

import time

from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.nlu import QueryParser
from querymind.orchestrator.exceptions import PipelineConfigurationError, PipelineExecutionError
from querymind.orchestrator.models import (
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
from querymind.schema_linker import SchemaLinker
from querymind.sql_execution import ExecutionStatus, SQLExecutionEngine, SQLExecutionResult
from querymind.sql_generation import SQLGenerationEngine
from querymind.sql_repair import RepairStatus, SQLRepairEngine
from querymind.sql_validation import SQLValidationEngine


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

    async def run(self, question: str) -> QueryMindResponse:
        """Run `question` through the complete pipeline.

        Raises `PipelineExecutionError` if any stage's own call raises.
        Never raises for a "soft" execution failure -- see the module
        docstring.
        """
        pipeline_started = time.perf_counter()
        stage_timings: list[StageTiming] = []
        current_stage = PipelineStage.NLU
        repair_attempted = False
        repair_performed = False
        generated_sql = None
        validation_result = None
        repair_result = None
        execution_result = None

        try:
            stage_started = time.perf_counter()
            query_context = self._nlu_parser.parse(question)
            stage_timings.append(self._timing(PipelineStage.NLU, stage_started))

            current_stage = PipelineStage.SCHEMA_LINKING
            stage_started = time.perf_counter()
            linked_context = self._schema_linker.link(query_context)
            stage_timings.append(self._timing(PipelineStage.SCHEMA_LINKING, stage_started))

            current_stage = PipelineStage.BUSINESS_KNOWLEDGE
            stage_started = time.perf_counter()
            self._business_knowledge_registry.load()
            stage_timings.append(self._timing(PipelineStage.BUSINESS_KNOWLEDGE, stage_started))

            current_stage = PipelineStage.RETRIEVAL
            stage_started = time.perf_counter()
            bundle = self._retrieval_engine.retrieve(linked_context)
            stage_timings.append(self._timing(PipelineStage.RETRIEVAL, stage_started))

            current_stage = PipelineStage.PROMPT_COMPILATION
            stage_started = time.perf_counter()
            compiled_prompt = self._prompt_compiler.compile(bundle, dialect=self._dialect)
            stage_timings.append(self._timing(PipelineStage.PROMPT_COMPILATION, stage_started))

            current_stage = PipelineStage.SQL_GENERATION
            stage_started = time.perf_counter()
            generated_sql = self._sql_generation_engine.generate(compiled_prompt)
            stage_timings.append(self._timing(PipelineStage.SQL_GENERATION, stage_started))
            # The LLM call itself already happened inside SQL_GENERATION (SQLGenerationEngine
            # wraps LLMAdapter internally) -- its own, independently measured latency is
            # carried on GeneratedSQL.llm_metrics, so LLM gets its own StageTiming without
            # this orchestrator calling LLMAdapter a second time.
            stage_timings.append(
                StageTiming(
                    stage=PipelineStage.LLM, latency_ms=generated_sql.llm_metrics.latency_ms
                )
            )

            current_stage = PipelineStage.SQL_VALIDATION
            stage_started = time.perf_counter()
            validation_result = self._sql_validation_engine.validate(generated_sql)
            stage_timings.append(self._timing(PipelineStage.SQL_VALIDATION, stage_started))

            final_generated_sql = generated_sql
            final_validation_result = validation_result
            repair_attempted = not validation_result.is_valid
            if repair_attempted:
                current_stage = PipelineStage.SQL_REPAIR
                stage_started = time.perf_counter()
                repair_result = self._sql_repair_engine.repair(
                    generated_sql, validation_result, bundle
                )
                stage_timings.append(self._timing(PipelineStage.SQL_REPAIR, stage_started))
                repair_performed = repair_result.status is RepairStatus.REPAIRED
                # Reuse the repair engine's own validation output -- never re-validate manually.
                final_generated_sql = repair_result.final_sql
                final_validation_result = repair_result.final_validation_result

            current_stage = PipelineStage.SQL_EXECUTION
            stage_started = time.perf_counter()
            execution_result = await self._sql_execution_engine.execute(
                final_generated_sql, final_validation_result
            )
            stage_timings.append(self._timing(PipelineStage.SQL_EXECUTION, stage_started))

            if execution_result.status is not ExecutionStatus.SUCCESS:
                return QueryMindResponse(
                    original_question=question,
                    business_answer=None,
                    generated_sql=final_generated_sql,
                    validation_result=final_validation_result,
                    repair_result=repair_result,
                    execution_result=execution_result,
                    statistics=self._statistics_builder.build(
                        total_latency_ms=self._elapsed_ms(pipeline_started),
                        stage_timings=tuple(stage_timings),
                        repair_attempted=repair_attempted,
                        repair_performed=repair_performed,
                    ),
                    status=PipelineStatus.FAILED,
                    error=self._execution_error_message(execution_result),
                )

            current_stage = PipelineStage.RESULT_FORMATTING
            stage_started = time.perf_counter()
            business_answer = self._result_formatter_engine.format(execution_result)
            stage_timings.append(self._timing(PipelineStage.RESULT_FORMATTING, stage_started))

            return QueryMindResponse(
                original_question=question,
                business_answer=business_answer,
                generated_sql=final_generated_sql,
                validation_result=final_validation_result,
                repair_result=repair_result,
                execution_result=execution_result,
                statistics=self._statistics_builder.build(
                    total_latency_ms=self._elapsed_ms(pipeline_started),
                    stage_timings=tuple(stage_timings),
                    repair_attempted=repair_attempted,
                    repair_performed=repair_performed,
                ),
                status=PipelineStatus.SUCCESS,
                error=None,
            )
        except Exception as exc:
            raise PipelineExecutionError(
                f"Pipeline failed at stage {current_stage.value!r}: {exc}",
                stage=current_stage,
                stage_timings=tuple(stage_timings),
                repair_attempted=repair_attempted,
                repair_performed=repair_performed,
                generated_sql=generated_sql,
                validation_result=validation_result,
                repair_result=repair_result,
                execution_result=execution_result,
            ) from exc

    @staticmethod
    def _timing(stage: PipelineStage, started: float) -> StageTiming:
        return StageTiming(stage=stage, latency_ms=PipelineRunner._elapsed_ms(started))

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000

    @staticmethod
    def _execution_error_message(execution_result: SQLExecutionResult) -> str:
        if execution_result.execution_error is not None:
            return execution_result.execution_error.message
        return f"SQL execution did not succeed (status={execution_result.status.value})."
