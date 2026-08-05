"""Tests for `querymind.sql_repair.prompt_builder`."""

from __future__ import annotations

from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.sql_repair.planner import RepairPlanner
from querymind.sql_repair.prompt_builder import RepairPromptBuilder, RepairPromptTemplate

from .conftest import make_generated_sql, make_issue, make_validation_result


class TestRepairPromptTemplate:
    def test_has_a_distinct_version_from_the_default_template(self) -> None:
        from querymind.prompt_compiler.templates import DefaultPromptTemplate

        assert RepairPromptTemplate().version != DefaultPromptTemplate().version

    def test_has_all_seven_sections(self) -> None:
        from querymind.prompt_compiler.models import SectionName

        names = {spec.name for spec in RepairPromptTemplate().section_specs}
        assert names == set(SectionName)

    def test_repurposed_headers_reflect_repair_semantics(self) -> None:
        from querymind.prompt_compiler.models import SectionName

        template = RepairPromptTemplate()
        assert template.spec_for(SectionName.RETRIEVED_EXAMPLES).header == "## SQL Requiring Repair"
        assert template.spec_for(SectionName.CONSTRAINT).header == "## Repair Rules"


class TestRepairPromptBuilder:
    def test_builds_a_compiled_prompt_with_the_repair_template_version(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert compiled.template_version == RepairPromptTemplate().version

    def test_examples_section_contains_the_broken_sql_and_errors(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(
            generated, errors=(make_issue("unknown_table", message="Table missing."),)
        )
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert "SELECT * FROM bogus;" in compiled.examples.content
        assert "unknown_table" in compiled.examples.content
        assert "Table missing." in compiled.examples.content

    def test_constraints_section_includes_repair_rules(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert "Repair ONLY the reported validation errors" in compiled.constraints.content
        assert "Do not invent a table" in compiled.constraints.content

    def test_system_section_is_repair_specific(self, bundle: RetrievedKnowledgeBundle) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert "SQL repair assistant" in compiled.system.content

    def test_business_and_schema_sections_are_unmodified_from_the_bundle(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert "customer" in compiled.business_context.content

    def test_dialect_is_taken_from_generated_sql(self, bundle: RetrievedKnowledgeBundle) -> None:
        from querymind.query_library.models import SQLDialect

        generated = make_generated_sql("SELECT * FROM bogus;", dialect=SQLDialect.MYSQL)
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert compiled.dialect is SQLDialect.MYSQL

    def test_two_builds_with_different_errors_do_not_leak_a_stale_cache_hit(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        # Regression guard for the exact bug the module docstring warns about:
        # a fresh PromptCompiler per call must never let a second, differently-
        # worded attempt reuse the first attempt's cached compiled prompt.
        generated = make_generated_sql("SELECT * FROM bogus;")
        first_validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        second_validation = make_validation_result(
            generated, errors=(make_issue("missing_group_by"),)
        )
        builder = RepairPromptBuilder()

        first_plan = RepairPlanner().plan(first_validation)
        second_plan = RepairPlanner().plan(second_validation)
        first_compiled = builder.build(bundle, generated, first_validation, first_plan)
        second_compiled = builder.build(bundle, generated, second_validation, second_plan)

        assert "unknown_table" in first_compiled.examples.content
        assert "missing_group_by" in second_compiled.examples.content
        assert "missing_group_by" not in first_compiled.examples.content


class TestRepairPromptRendersWithItsOwnTemplate:
    """Regression coverage for the Phase 12 bug: CompiledPrompt.as_text() used to always
    render with DefaultPromptTemplate, silently ignoring RepairPromptTemplate."""

    def test_as_text_shows_the_repair_specific_headers(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        text = compiled.as_text()

        assert "## SQL Requiring Repair" in text
        assert "## Repair Rules" in text

    def test_as_text_never_shows_the_generic_default_headers(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        # This is the exact scenario that was broken: a compiled repair prompt
        # rendering under "## Similar Examples"/"## Constraints" (DefaultPromptTemplate's
        # headers) instead of its own RepairPromptTemplate headers.
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        text = compiled.as_text()

        assert "## Similar Examples" not in text
        assert "## Constraints" not in text

    def test_as_text_still_contains_the_broken_sql_and_errors(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(
            generated, errors=(make_issue("unknown_table", message="Table missing."),)
        )
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        text = compiled.as_text()

        assert "SELECT * FROM bogus;" in text
        assert "Table missing." in text

    def test_compiled_prompt_template_field_is_the_repair_template(
        self, bundle: RetrievedKnowledgeBundle
    ) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)

        compiled = RepairPromptBuilder().build(bundle, generated, validation, plan)
        assert compiled.template == RepairPromptTemplate()
