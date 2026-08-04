"""The SQL Generation Engine — QueryMind Phase 11A.

Converts a `querymind.prompt_compiler.CompiledPrompt` into a
`GeneratedSQL`, using the existing `querymind.llm.LLMAdapter`. It does
**not** validate SQL, does **not** execute SQL, does **not** repair SQL,
and does **not** modify prompts — `GeneratedSQL.sql` is exactly what the
LLM produced, extracted and cosmetically normalized, nothing more.

The public surface is `SQLGenerationEngine.generate`.
"""

from __future__ import annotations

from querymind.sql_generation.cache import GeneratedSQLCache, NoOpGeneratedSQLCache
from querymind.sql_generation.engine import SQLGenerationEngine
from querymind.sql_generation.exceptions import SQLExtractionError, SQLGenerationError
from querymind.sql_generation.extractor import ExtractionResult, SQLExtractor
from querymind.sql_generation.formatter import GeneratedSQLFormatter
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_generation.normalizer import SQLNormalizer
from querymind.sql_generation.parser import StatementTypeDetector
from querymind.sql_generation.statistics import build_statistics

__all__ = [
    "ExtractionMethod",
    "ExtractionResult",
    "GeneratedSQL",
    "GeneratedSQLCache",
    "GeneratedSQLFormatter",
    "NoOpGeneratedSQLCache",
    "SQLExtractionError",
    "SQLExtractor",
    "SQLGenerationEngine",
    "SQLGenerationError",
    "SQLGenerationStatistics",
    "SQLNormalizer",
    "SQLStatementType",
    "StatementTypeDetector",
    "build_statistics",
]
