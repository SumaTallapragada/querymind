"""The SQL Repair Engine: automatically repairs invalid SQL using existing infrastructure.

`SQLRepairEngine` is the single public entry point for this package. It
orchestrates *only* — every actual piece of work is delegated to a
dedicated, single-responsibility, constructor-injected collaborator:
`RepairPlanner` categorizes issues, `RepairPromptBuilder` builds the
repair prompt (reusing the existing Prompt Compiler),
`SQLRepairLLMAdapter` calls the existing `LLMAdapter`,
`RepairedSQLExtractor` extracts the repaired SQL,
`RepairValidator` re-validates it via the existing `SQLValidationEngine`,
and `RepairStrategy` decides when to stop. The engine never builds a
prompt, calls a provider, validates, extracts SQL, or decides repair
strategy itself.

The loop is deterministic and bounded (`RepairStrategy.max_attempts`,
default 3). The original `GeneratedSQL` passed in is never mutated —
every attempt produces a new `GeneratedSQL` artifact, and the complete
history of every attempt is preserved in the returned `SQLRepairResult`,
never overwritten. This package never executes, optimizes, or explains
SQL — repair is where it stops.
"""

from __future__ import annotations

import time

from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_repair.llm_adapter import SQLRepairLLMAdapter
from querymind.sql_repair.models import (
    RepairAttempt,
    RepairHistory,
    RepairStatistics,
    SQLRepairResult,
)
from querymind.sql_repair.parser import RepairedSQLExtractor
from querymind.sql_repair.planner import RepairPlanner
from querymind.sql_repair.prompt_builder import RepairPromptBuilder
from querymind.sql_repair.strategy import RepairStrategy
from querymind.sql_repair.validator import RepairValidator
from querymind.sql_validation.models import SQLValidationResult


class SQLRepairEngine:
    """Repairs invalid SQL by orchestrating the existing Prompt Compiler, LLM Adapter, and SQL
    Validation Engine over a bounded, deterministic loop.

    Every collaborator is constructor-injected with a sensible default,
    so a caller can swap in a different planner, prompt template,
    extractor, or stopping strategy without touching this class.
    """

    def __init__(
        self,
        repair_llm_adapter: SQLRepairLLMAdapter,
        repair_validator: RepairValidator,
        planner: RepairPlanner | None = None,
        prompt_builder: RepairPromptBuilder | None = None,
        extractor: RepairedSQLExtractor | None = None,
        strategy: RepairStrategy | None = None,
    ) -> None:
        self._repair_llm_adapter = repair_llm_adapter
        self._repair_validator = repair_validator
        self._planner = planner or RepairPlanner()
        self._prompt_builder = prompt_builder or RepairPromptBuilder()
        self._extractor = extractor or RepairedSQLExtractor()
        self._strategy = strategy or RepairStrategy()

    def repair(
        self,
        generated_sql: GeneratedSQL,
        validation_result: SQLValidationResult,
        bundle: RetrievedKnowledgeBundle,
    ) -> SQLRepairResult:
        """Repair `generated_sql`, whose `validation_result` reported at least one error.

        `bundle` is the `RetrievedKnowledgeBundle` the original SQL was
        generated from — needed so the repair prompt can reuse the
        existing Prompt Compiler with real business/schema/relationship
        context, since neither `GeneratedSQL` nor `SQLValidationResult`
        retain it.

        Never modifies `generated_sql` or `validation_result`. Never
        raises for SQL that remains invalid after every attempt — that
        is reported as `RepairStatus.MAX_ATTEMPTS_REACHED`/`NO_PROGRESS`
        data on the returned `SQLRepairResult`, not an exception.
        Propagates whatever the underlying `LLMAdapter`/`SQLValidationEngine`
        raise for their own genuine failures (an exhausted retry policy,
        an unloaded registry, ...), exactly as `SQLGenerationEngine` does.
        """
        started = time.perf_counter()
        history: list[RepairAttempt] = []
        current_sql = generated_sql
        current_validation = validation_result
        attempt_number = 1

        while True:
            plan = self._planner.plan(current_validation)
            if not plan.is_repairable:
                break

            compiled_prompt = self._prompt_builder.build(
                bundle, current_sql, current_validation, plan
            )
            llm_response = self._repair_llm_adapter.repair(compiled_prompt)
            repaired_sql = self._extractor.extract(llm_response, dialect=current_sql.dialect)
            new_validation = self._repair_validator.validate(repaired_sql)

            history.append(
                RepairAttempt(
                    attempt_number=attempt_number,
                    repair_reason=plan.primary_reason,
                    input_sql=current_sql.sql,
                    repaired_sql=repaired_sql.sql,
                    validation_result=new_validation,
                    prompt_version=compiled_prompt.template_version,
                    llm_metrics=llm_response.metrics,
                    success=new_validation.is_valid,
                )
            )
            current_sql = repaired_sql
            current_validation = new_validation

            if not self._strategy.should_continue(tuple(history)):
                break
            attempt_number += 1

        status = self._strategy.final_status(tuple(history))
        repair_latency_ms = (time.perf_counter() - started) * 1000
        statistics = self._build_statistics(
            history=tuple(history), repair_latency_ms=repair_latency_ms
        )

        return SQLRepairResult(
            original_sql=generated_sql,
            final_sql=current_sql,
            final_validation_result=current_validation,
            history=RepairHistory(attempts=tuple(history)),
            statistics=statistics,
            status=status,
        )

    @staticmethod
    def _build_statistics(
        *, history: tuple[RepairAttempt, ...], repair_latency_ms: float
    ) -> RepairStatistics:
        successful = sum(1 for attempt in history if attempt.success)
        failed = len(history) - successful
        average_validation_latency_ms = (
            sum(
                attempt.validation_result.validation_statistics.validation_latency_ms
                for attempt in history
            )
            / len(history)
            if history
            else 0.0
        )
        return RepairStatistics(
            attempt_count=len(history),
            successful_repairs=successful,
            failed_repairs=failed,
            repair_latency_ms=repair_latency_ms,
            average_validation_latency_ms=average_validation_latency_ms,
        )
