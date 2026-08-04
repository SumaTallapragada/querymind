"""Shared fixtures: a small, fully synthetic catalog for business-knowledge tests.

Built directly from `querymind.business_knowledge.models` (never from the
real shipped `concepts.yaml`) so every test controls its catalog
precisely — matching and cache behavior are exercised against exact,
known inputs. `tests/business_knowledge/test_integration.py` separately
exercises the real shipped catalog.
"""

from __future__ import annotations

import pytest

from querymind.business_knowledge.catalog import build_catalog
from querymind.business_knowledge.models import (
    BusinessConcept,
    BusinessConceptType,
    BusinessFormula,
    BusinessKnowledgeCatalog,
)


@pytest.fixture
def sample_concepts() -> tuple[BusinessConcept, ...]:
    """Three concepts exercising every match tier plus a PARTIAL collision case.

    - `revenue`: EXACT (name "Revenue"), ALIAS ("Turnover"), SYNONYM
      (related term "Sales"), formula attached.
    - `average_order_value`: ALIAS ("AOV"), and its name "Average Order
      Value" is a PARTIAL match target for "order value".
    - `order_value`: a *different* concept whose name is "Order Value" —
      deliberately close to `average_order_value`'s name, so partial
      matching has a real ambiguity-shaped case to resolve
      deterministically (by catalog order, since no confidence scoring
      is in scope for this engine).
    """
    return (
        BusinessConcept(
            id="revenue",
            name="Revenue",
            concept_type=BusinessConceptType.METRIC,
            description="Total amount charged to customers.",
            aliases=("Turnover",),
            related_terms=("Sales",),
            example_questions=("What is our revenue?",),
            calculation_description="Sum of order totals.",
            formula=BusinessFormula(
                expression="SUM(orders.total_amount)", variables=("total_amount",)
            ),
            preferred_schema_objects=("orders.total_amount",),
        ),
        BusinessConcept(
            id="average_order_value",
            name="Average Order Value",
            concept_type=BusinessConceptType.METRIC,
            description="Average amount spent per order.",
            aliases=("AOV",),
            related_terms=(),
            example_questions=(),
            calculation_description="Revenue divided by order count.",
            preferred_schema_objects=("orders.total_amount",),
        ),
        BusinessConcept(
            id="order_value",
            name="Order Value",
            concept_type=BusinessConceptType.METRIC,
            description="The total monetary amount of a single order.",
            aliases=(),
            related_terms=(),
            example_questions=(),
            calculation_description="The final charged total for one order.",
            preferred_schema_objects=("orders.total_amount",),
        ),
        BusinessConcept(
            id="top_customer",
            name="Top Customer",
            concept_type=BusinessConceptType.SEGMENT,
            description="A customer ranked highest by spend.",
            aliases=("VIP Customer",),
            related_terms=(),
            example_questions=(),
            calculation_description="Ranked by total order value.",
            preferred_schema_objects=("customers.customer_id",),
        ),
    )


@pytest.fixture
def sample_catalog(sample_concepts: tuple[BusinessConcept, ...]) -> BusinessKnowledgeCatalog:
    return build_catalog(sample_concepts)
