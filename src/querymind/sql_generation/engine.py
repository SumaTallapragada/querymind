"""The SQL Generation Engine: turns a `CompiledPrompt` into a `GeneratedSQL`.

`SQLGenerationEngine` is the single public entry point for this package.
It runs the seven-step pipeline: send the compiled prompt to the
existing `LLMAdapter` (steps 1-2), extract SQL text from the response
(step 3), normalize it (step 4), construct `GeneratedSQL` (step 5),
collect generation statistics (step 6), and return it (step 7). It never
validates, executes, or repairs SQL, and never modifies the prompt it's
given — the prompt was already fully built by the time it reaches here.
"""

from __future__ import annotations

import time

from querymind.llm.adapter import LLMAdapter
from querymind.prompt_compiler.models import CompiledPrompt
from querymind.sql_generation.extractor import SQLExtractor
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_generation.normalizer import SQLNormalizer
from querymind.sql_generation.parser import StatementTypeDetector
from querymind.sql_generation.statistics import build_statistics


class SQLGenerationEngine:
    """Converts a `CompiledPrompt` into a `GeneratedSQL` using the existing `LLMAdapter`.

    Every collaborator — the LLM adapter, the extractor, the normalizer,
    the statement-type detector — is constructor-injected with a
    sensible default, so a caller can swap in a different LLM adapter or
    a different extraction/normalization strategy without touching this
    class.
    """

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        extractor: SQLExtractor | None = None,
        normalizer: SQLNormalizer | None = None,
        statement_type_detector: StatementTypeDetector | None = None,
    ) -> None:
        self._llm_adapter = llm_adapter
        self._extractor = extractor or SQLExtractor()
        self._normalizer = normalizer or SQLNormalizer()
        self._statement_type_detector = statement_type_detector or StatementTypeDetector()

    def generate(self, compiled_prompt: CompiledPrompt) -> GeneratedSQL:
        """Generate SQL for `compiled_prompt`.

        Raises `querymind.sql_generation.exceptions.SQLExtractionError`
        if the LLM's response contains no extractable SQL text, or
        whatever `querymind.llm.exceptions.LLMError` subclass the
        underlying `LLMAdapter.generate` call raises.
        """
        started = time.perf_counter()

        # Steps 1-2: send to the existing LLM Adapter, receive its response.
        llm_response = self._llm_adapter.generate(compiled_prompt)

        # Step 3: extract SQL text from the raw response.
        extraction = self._extractor.extract(llm_response.content)

        # Step 4: normalize the extracted SQL.
        normalized_sql = self._normalizer.normalize(extraction.sql)

        # Step 6: collect generation statistics (computed here, embedded in step 5's result).
        statistics = build_statistics(
            extraction_method=extraction.method,
            raw_sql=extraction.sql,
            normalized_sql=normalized_sql,
            started=started,
        )

        # Step 5: construct GeneratedSQL.
        generated = GeneratedSQL(
            sql=normalized_sql,
            statement_type=self._statement_type_detector.detect(normalized_sql),
            raw_llm_content=llm_response.content,
            dialect=compiled_prompt.dialect,
            llm_metrics=llm_response.metrics,
            statistics=statistics,
        )

        # Step 7: return.
        return generated
