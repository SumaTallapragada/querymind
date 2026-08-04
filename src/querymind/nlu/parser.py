"""The NLU pipeline: orchestrates every extraction stage into one `QueryContext`.

`QueryParser` is the single public entry point for this package. Every
stage is injected through the constructor as a small `Protocol`-typed
collaborator (`Normalizer`, `IntentClassifier`, `EntityExtractor`, ...),
each with a deterministic, rule-based default implementation — callers
that need different parsing behavior swap in their own implementation of
the relevant protocol without touching this class, and every stage
remains independently unit-testable without going through the full
pipeline (dependency inversion: `QueryParser` depends on the protocols
in each stage's module, never on the default implementations directly).
"""

from __future__ import annotations

from querymind.nlu.entities import DefaultEntityExtractor, EntityExtractionResult, EntityExtractor
from querymind.nlu.exceptions import EmptyQuestionError
from querymind.nlu.filters import DefaultFilterExtractor, FilterExtractor
from querymind.nlu.intents import DefaultIntentClassifier, IntentClassifier
from querymind.nlu.limits import DefaultLimitExtractor, LimitExtractor
from querymind.nlu.metrics import DefaultMetricExtractor, MetricExtractor
from querymind.nlu.models import (
    AggregationType,
    FilterExpression,
    Intent,
    MetricExpression,
    QueryContext,
)
from querymind.nlu.normalizer import DefaultNormalizer, Normalizer
from querymind.nlu.sorting import DefaultSortExtractor, SortExtractor
from querymind.nlu.time import DefaultTimeExtractor, TimeExtractor

#: `Intent` values that reduce to exactly one `AggregationType`.
_INTENT_AGGREGATION: dict[Intent, AggregationType] = {
    Intent.COUNT: AggregationType.COUNT,
    Intent.SUM: AggregationType.SUM,
    Intent.AVERAGE: AggregationType.AVERAGE,
    Intent.MIN: AggregationType.MIN,
    Intent.MAX: AggregationType.MAX,
}


class QueryParser:
    """Parses a natural language question into a `QueryContext`.

    Runs the fixed pipeline: normalize -> classify intent -> extract
    entities -> extract metrics -> extract filters -> extract time ->
    extract sort -> extract limit -> assemble. Nothing here inspects a
    database or a metadata registry, calls an LLM, or generates SQL —
    see the `querymind.nlu` package docstring for that boundary.
    """

    def __init__(
        self,
        normalizer: Normalizer | None = None,
        intent_classifier: IntentClassifier | None = None,
        entity_extractor: EntityExtractor | None = None,
        metric_extractor: MetricExtractor | None = None,
        filter_extractor: FilterExtractor | None = None,
        time_extractor: TimeExtractor | None = None,
        sort_extractor: SortExtractor | None = None,
        limit_extractor: LimitExtractor | None = None,
    ) -> None:
        self._normalizer = normalizer or DefaultNormalizer()
        self._intent_classifier = intent_classifier or DefaultIntentClassifier()
        self._entity_extractor = entity_extractor or DefaultEntityExtractor()
        self._metric_extractor = metric_extractor or DefaultMetricExtractor()
        self._filter_extractor = filter_extractor or DefaultFilterExtractor()
        self._time_extractor = time_extractor or DefaultTimeExtractor()
        self._sort_extractor = sort_extractor or DefaultSortExtractor()
        self._limit_extractor = limit_extractor or DefaultLimitExtractor()

    def parse(self, question: str) -> QueryContext:
        """Parse one natural language question into a `QueryContext`.

        Raises `EmptyQuestionError` if `question` is empty or
        whitespace-only. Every other input always produces a
        `QueryContext`, falling back to `Intent.SELECT` and a low
        `confidence` when nothing more specific is recognized.
        """
        if not question or not question.strip():
            raise EmptyQuestionError("question must not be empty")

        normalized = self._normalizer.normalize(question)
        intent, intent_confidence = self._intent_classifier.classify(normalized)
        entity_result = self._entity_extractor.extract(normalized)
        metrics = self._metric_extractor.extract(normalized)
        filters = self._filter_extractor.extract(normalized)
        time_expression = self._time_extractor.extract(normalized)
        sort = self._sort_extractor.extract(normalized, metrics)
        limit = self._limit_extractor.extract(normalized)

        aggregation = self._resolve_aggregation(intent, metrics)
        business_concepts = self._collect_business_concepts(entity_result, metrics, filters)
        confidence = self._compute_confidence(
            intent_confidence=intent_confidence,
            has_entity=entity_result.primary_entity is not None,
            has_metric=bool(metrics),
            has_filter=bool(filters),
            has_time=time_expression is not None,
        )

        return QueryContext(
            original_question=question,
            normalized_question=normalized,
            intent=intent,
            primary_entity=entity_result.primary_entity,
            secondary_entities=entity_result.secondary_entities,
            business_concepts=business_concepts,
            metrics=metrics,
            dimensions=entity_result.dimensions,
            filters=filters,
            time_expression=time_expression,
            sort=sort,
            limit=limit,
            aggregation=aggregation,
            confidence=confidence,
        )

    @staticmethod
    def _resolve_aggregation(
        intent: Intent, metrics: tuple[MetricExpression, ...]
    ) -> AggregationType | None:
        """Resolve the overall `QueryContext.aggregation` implied by `intent`.

        `COUNT`/`SUM`/`AVERAGE`/`MIN`/`MAX` intents map directly to their
        matching reducer. `AGGREGATION` (a grouped breakdown with no
        single named reducer, e.g. "revenue by region") borrows the first
        explicitly-requested per-metric aggregation if there is one, else
        defaults to `SUM` when at least one metric was found — grouped
        breakdowns of a business metric are a sum far more often than
        any other reducer. Every other intent has no single aggregation.
        """
        if intent in _INTENT_AGGREGATION:
            return _INTENT_AGGREGATION[intent]
        if intent is Intent.AGGREGATION:
            for metric in metrics:
                if metric.aggregation is not None:
                    return metric.aggregation
            return AggregationType.SUM if metrics else None
        return None

    @staticmethod
    def _collect_business_concepts(
        entity_result: EntityExtractionResult,
        metrics: tuple[MetricExpression, ...],
        filters: tuple[FilterExpression, ...],
    ) -> tuple[str, ...]:
        """Union every canonical concept recognized anywhere in the question, de-duplicated in order."""
        concepts: list[str] = []
        if entity_result.primary_entity is not None:
            concepts.append(entity_result.primary_entity)
        concepts.extend(entity_result.secondary_entities)
        concepts.extend(entity_result.dimensions)
        concepts.extend(metric.name for metric in metrics)
        concepts.extend(expression.field for expression in filters)

        seen: set[str] = set()
        ordered: list[str] = []
        for concept in concepts:
            if concept not in seen:
                seen.add(concept)
                ordered.append(concept)
        return tuple(ordered)

    @staticmethod
    def _compute_confidence(
        *,
        intent_confidence: float,
        has_entity: bool,
        has_metric: bool,
        has_filter: bool,
        has_time: bool,
    ) -> float:
        """A deterministic heuristic score, not a calibrated probability.

        Starts from how confidently the intent rule matched, then adds a
        small bonus for each additional signal (entity, metric, filter,
        time) the pipeline was able to ground the question in, capped at
        1.0.
        """
        score = intent_confidence
        if has_entity:
            score += 0.05
        if has_metric:
            score += 0.05
        if has_filter:
            score += 0.03
        if has_time:
            score += 0.02
        return round(min(score, 1.0), 4)


def parse_question(question: str) -> QueryContext:
    """Convenience wrapper around `QueryParser().parse` for one-off parsing."""
    return QueryParser().parse(question)
