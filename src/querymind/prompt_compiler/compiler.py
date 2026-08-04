"""The Prompt Compiler: turns a `RetrievedKnowledgeBundle` into a `CompiledPrompt`.

`PromptCompiler` is the single public entry point for this package. It
runs the ten-step compilation pipeline: build all seven sections (steps
1-7, one dedicated builder each), validate the freshly built sections
(step 8), trim to fit the token budget (step 9), and assemble the final
`CompiledPrompt` plus its statistics (step 10) — validating once more on
the final, post-trim sections, since "token budget respected" can only
be meaningfully checked after trimming has actually run. Nothing here
calls an LLM, generates SQL, or knows anything about a specific model
provider.
"""

from __future__ import annotations

import time
from typing import cast

from querymind.prompt_compiler.budget import DEFAULT_MAX_TOKENS, PromptBudgetManager
from querymind.prompt_compiler.cache import InMemoryPromptCache, PromptCache, bundle_content_hash
from querymind.prompt_compiler.models import (
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptSection,
    PromptStatistics,
    RelationshipSection,
    SchemaSection,
    SectionTokenUsage,
    SystemSection,
)
from querymind.prompt_compiler.sections import (
    BusinessSectionBuilder,
    ConstraintSectionBuilder,
    ExampleSectionBuilder,
    OutputSectionBuilder,
    RelationshipSectionBuilder,
    SchemaSectionBuilder,
    SystemSectionBuilder,
)
from querymind.prompt_compiler.templates import DefaultPromptTemplate, PromptTemplate
from querymind.prompt_compiler.validator import PromptValidator
from querymind.query_library.models import SQLDialect
from querymind.retrieval.models import RetrievedKnowledgeBundle


class PromptCompiler:
    """Compiles a `RetrievedKnowledgeBundle` into a `CompiledPrompt`.

    Every collaborator — the template, the seven section builders, the
    budget manager, the validator, the cache — is constructor-injected
    with a sensible default, so a caller can swap in a different
    template, a stricter token budget, or a different cache without
    touching this class.
    """

    def __init__(
        self,
        template: PromptTemplate | None = None,
        budget_manager: PromptBudgetManager | None = None,
        validator: PromptValidator | None = None,
        cache: PromptCache | None = None,
        system_builder: SystemSectionBuilder | None = None,
        business_builder: BusinessSectionBuilder | None = None,
        schema_builder: SchemaSectionBuilder | None = None,
        relationship_builder: RelationshipSectionBuilder | None = None,
        example_builder: ExampleSectionBuilder | None = None,
        constraint_builder: ConstraintSectionBuilder | None = None,
        output_builder: OutputSectionBuilder | None = None,
    ) -> None:
        self._template = template or DefaultPromptTemplate()
        self._budget_manager = budget_manager or PromptBudgetManager(DEFAULT_MAX_TOKENS)
        self._validator = validator or PromptValidator(self._budget_manager.max_tokens)
        self._cache = cache or InMemoryPromptCache()
        self._system_builder = system_builder or SystemSectionBuilder()
        self._business_builder = business_builder or BusinessSectionBuilder()
        self._schema_builder = schema_builder or SchemaSectionBuilder()
        self._relationship_builder = relationship_builder or RelationshipSectionBuilder()
        self._example_builder = example_builder or ExampleSectionBuilder()
        self._constraint_builder = constraint_builder or ConstraintSectionBuilder()
        self._output_builder = output_builder or OutputSectionBuilder()

    def compile(
        self, bundle: RetrievedKnowledgeBundle, dialect: SQLDialect = SQLDialect.POSTGRESQL
    ) -> CompiledPrompt:
        """Compile `bundle` into a `CompiledPrompt` targeting `dialect`.

        Returns a cached prompt if an equivalent `(bundle, template,
        dialect)` combination was already compiled and was valid; never
        returns a *cached copy* of a prompt that failed final validation
        — see `querymind.prompt_compiler.cache`.
        """
        cache_key = (bundle_content_hash(bundle), self._template.version, dialect.value)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        started = time.perf_counter()

        # Steps 1-7: build every section independently. Each builder
        # knows only its own section — the specific concrete subtype
        # returned (SystemSection, BusinessSection, ...) is exactly what
        # each one always returns, by construction.
        system = self._system_builder.build(bundle, dialect)
        business = self._business_builder.build(bundle, dialect)
        schema = self._schema_builder.build(bundle, dialect)
        relationships = self._relationship_builder.build(bundle, dialect)
        examples = self._example_builder.build(bundle, dialect)
        constraints = self._constraint_builder.build(bundle, dialect)
        output_format = self._output_builder.build(bundle, dialect)

        built_sections: tuple[PromptSection, ...] = (
            system,
            business,
            schema,
            relationships,
            examples,
            constraints,
            output_format,
        )

        # Step 8: validate the freshly built (untrimmed) sections —
        # surfaces builder bugs (an empty required section, duplicate
        # examples) independently of whatever trimming is about to do.
        self._validator.validate(built_sections)

        # Step 9: token budget optimization. `PromptBudgetManager.enforce`
        # returns each section's own concrete type unchanged (it only
        # ever calls `.model_copy()`, which preserves the subclass), so
        # the casts below are simply restoring the specific static types
        # `enforce`'s `Sequence[PromptSection] -> tuple[PromptSection, ...]`
        # signature necessarily widens away.
        trimmed = {
            section.name: section for section in self._budget_manager.enforce(built_sections)
        }

        # Step 10: assemble the final CompiledPrompt.
        compiled = CompiledPrompt(
            system=cast(SystemSection, trimmed[system.name]),
            business_context=cast(BusinessSection, trimmed[business.name]),
            schema_context=cast(SchemaSection, trimmed[schema.name]),
            relationships=cast(RelationshipSection, trimmed[relationships.name]),
            examples=cast(ExampleSection, trimmed[examples.name]),
            constraints=cast(ConstraintSection, trimmed[constraints.name]),
            output_format=cast(OutputSection, trimmed[output_format.name]),
            statistics=self._build_statistics(
                trimmed_sections=tuple(trimmed.values()), started=started
            ),
            template_version=self._template.version,
            dialect=dialect,
        )

        final_report = self._validator.validate(compiled.all_sections())
        if final_report.is_valid:
            self._cache.set(cache_key, compiled)

        return compiled

    @staticmethod
    def _build_statistics(
        *, trimmed_sections: tuple[PromptSection, ...], started: float
    ) -> PromptStatistics:
        example_section = next(
            (section for section in trimmed_sections if isinstance(section, ExampleSection)), None
        )
        schema_section = next(
            (section for section in trimmed_sections if isinstance(section, SchemaSection)), None
        )
        return PromptStatistics(
            estimated_total_tokens=sum(section.estimated_tokens for section in trimmed_sections),
            section_token_usage=tuple(
                SectionTokenUsage(section=section.name, estimated_tokens=section.estimated_tokens)
                for section in trimmed_sections
            ),
            retrieved_example_count=len(example_section.example_ids)
            if example_section is not None
            else 0,
            schema_object_count=len(schema_section.schema_objects)
            if schema_section is not None
            else 0,
            compilation_latency_ms=(time.perf_counter() - started) * 1000,
        )
