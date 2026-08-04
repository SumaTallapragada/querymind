"""Exceptions raised by the natural language understanding engine."""

from __future__ import annotations


class NLUError(Exception):
    """Base class for every exception raised by `querymind.nlu`."""


class EmptyQuestionError(NLUError):
    """Raised when `QueryParser.parse` is given an empty or whitespace-only question."""
