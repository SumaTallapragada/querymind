"""Domain-specific exceptions for the Business Knowledge Engine.

Every failure mode a caller of `querymind.business_knowledge` can hit is
one of these — never a bare `KeyError`/`ValueError` leaking out of an
internal dict/list lookup. Mirrors `querymind.metadata.exceptions`'
reasoning exactly: a specific, documented exception type a consumer can
catch, instead of guessing at what an engine-internal lookup miss looks
like.
"""

from __future__ import annotations


class BusinessKnowledgeError(Exception):
    """Base class for every exception raised by `querymind.business_knowledge`."""


class KnowledgeNotLoadedError(BusinessKnowledgeError):
    """Raised when the catalog is read before `BusinessKnowledgeRegistry.load()` runs."""

    def __init__(self) -> None:
        super().__init__(
            "Business knowledge catalog has not been loaded yet. "
            "Call BusinessKnowledgeRegistry.load() first."
        )


class ConceptNotFoundError(BusinessKnowledgeError):
    """Raised when a requested concept id does not exist in the loaded catalog."""

    def __init__(self, concept_id: str) -> None:
        self.concept_id = concept_id
        super().__init__(
            f"No business concept with id {concept_id!r} exists in the loaded catalog."
        )


class DuplicateConceptError(BusinessKnowledgeError):
    """Raised when two catalog entries declare the same concept id."""

    def __init__(self, concept_id: str) -> None:
        self.concept_id = concept_id
        super().__init__(f"Concept id {concept_id!r} is declared more than once in the catalog.")


class CatalogLoadError(BusinessKnowledgeError):
    """Raised when the concepts data source fails to load or validate."""

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Failed to load business knowledge catalog from {source!r}: {reason}")
