"""The SQL Repair Engine — QueryMind Phase 12.

Automatically repairs SQL that `querymind.sql_validation.SQLValidationEngine`
found invalid, using the existing Prompt Compiler, LLM Adapter, and SQL
Validation Engine over a bounded, deterministic loop (default 3
attempts). It does **not** execute SQL, does **not** optimize SQL, and
does **not** explain SQL — those are later phases. The original
`GeneratedSQL` is never mutated; every attempt produces a new artifact,
and the complete attempt history is always preserved.

The public surface is `SQLRepairEngine.repair`.
"""

from __future__ import annotations

from querymind.sql_repair.cache import NoOpSQLRepairCache, SQLRepairCache
from querymind.sql_repair.engine import SQLRepairEngine
from querymind.sql_repair.exceptions import (
    RepairedSQLExtractionError,
    SQLRepairConfigurationError,
    SQLRepairError,
)
from querymind.sql_repair.llm_adapter import SQLRepairLLMAdapter
from querymind.sql_repair.models import (
    RepairAttempt,
    RepairHistory,
    RepairReason,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)
from querymind.sql_repair.parser import RepairedSQLExtractor
from querymind.sql_repair.planner import RepairCategory, RepairPlan, RepairPlanner
from querymind.sql_repair.prompt_builder import RepairPromptBuilder, RepairPromptTemplate
from querymind.sql_repair.serializer import SQLRepairSerializer
from querymind.sql_repair.strategy import DEFAULT_MAX_ATTEMPTS, RepairStrategy
from querymind.sql_repair.validator import RepairValidator

__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "NoOpSQLRepairCache",
    "RepairAttempt",
    "RepairCategory",
    "RepairHistory",
    "RepairPlan",
    "RepairPlanner",
    "RepairPromptBuilder",
    "RepairPromptTemplate",
    "RepairReason",
    "RepairStatistics",
    "RepairStatus",
    "RepairStrategy",
    "RepairValidator",
    "RepairedSQLExtractionError",
    "RepairedSQLExtractor",
    "SQLRepairCache",
    "SQLRepairConfigurationError",
    "SQLRepairEngine",
    "SQLRepairError",
    "SQLRepairLLMAdapter",
    "SQLRepairResult",
    "SQLRepairSerializer",
]
