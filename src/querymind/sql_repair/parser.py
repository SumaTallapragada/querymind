"""Extracts a repaired `GeneratedSQL` from a repair LLM response.

Composes `querymind.sql_generation`'s own `SQLExtractor`, `SQLNormalizer`,
`StatementTypeDetector`, and `build_statistics` — the exact same
components `SQLGenerationEngine` itself uses for a first-pass generation
— so a repaired response is extracted, normalized, and statement-typed
identically. This module duplicates none of their logic, only composes
them; `SQLGenerationEngine.generate()` isn't reusable directly here
because it owns its own LLM call internally, whereas the repair pipeline
needs the LLM call (`SQLRepairLLMAdapter`) and the extraction step kept
separate. Never validates the result — that is `RepairValidator`'s job.
"""

from __future__ import annotations

import time

from querymind.llm.models import LLMResponse
from querymind.query_library.models import SQLDialect
from querymind.sql_generation.exceptions import SQLExtractionError
from querymind.sql_generation.extractor import SQLExtractor
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_generation.normalizer import SQLNormalizer
from querymind.sql_generation.parser import StatementTypeDetector
from querymind.sql_generation.statistics import build_statistics
from querymind.sql_repair.exceptions import RepairedSQLExtractionError


class RepairedSQLExtractor:
    """Extracts and normalizes the SQL text a repair LLM call produced, as a `GeneratedSQL`."""

    def __init__(
        self,
        extractor: SQLExtractor | None = None,
        normalizer: SQLNormalizer | None = None,
        statement_type_detector: StatementTypeDetector | None = None,
    ) -> None:
        self._extractor = extractor or SQLExtractor()
        self._normalizer = normalizer or SQLNormalizer()
        self._statement_type_detector = statement_type_detector or StatementTypeDetector()

    def extract(self, llm_response: LLMResponse, *, dialect: SQLDialect) -> GeneratedSQL:
        """Extract the repaired SQL from `llm_response` into a new `GeneratedSQL`.

        Raises `RepairedSQLExtractionError` if `llm_response.content`
        contains no usable SQL text at all.
        """
        started = time.perf_counter()
        try:
            extraction = self._extractor.extract(llm_response.content)
        except SQLExtractionError as exc:
            raise RepairedSQLExtractionError(str(exc)) from exc

        normalized_sql = self._normalizer.normalize(extraction.sql)
        statistics = build_statistics(
            extraction_method=extraction.method,
            raw_sql=extraction.sql,
            normalized_sql=normalized_sql,
            started=started,
        )
        return GeneratedSQL(
            sql=normalized_sql,
            statement_type=self._statement_type_detector.detect(normalized_sql),
            raw_llm_content=llm_response.content,
            dialect=dialect,
            llm_metrics=llm_response.metrics,
            statistics=statistics,
        )
