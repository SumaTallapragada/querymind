"""Ambiguity detection: deciding whether a ranked candidate list resolves confidently.

The one place "never silently guess" is actually enforced. Every other
module in this package only ever *proposes* candidates; `AmbiguityDetector`
is what decides whether the top proposal is trustworthy enough to accept
automatically, or whether the caller needs to be told "this could be
several things" instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from querymind.schema_linker.models import LinkCandidate


def _describe(candidate: LinkCandidate) -> str:
    """`"table.column"` for a column candidate, or just `"table"` for a table candidate."""
    if candidate.column_name is None:
        return candidate.table_name
    return f"{candidate.table_name}.{candidate.column_name}"


@dataclass(frozen=True, slots=True)
class AmbiguityDecision:
    """The outcome of `AmbiguityDetector.decide`."""

    is_confident: bool
    reason: str | None = None


class AmbiguityDetector:
    """Decides whether a ranked candidate list resolves confidently or is ambiguous.

    A concept resolves confidently when its top candidate clears a
    minimum confidence bar *and* is separated from the next-best
    candidate by a minimum margin. Either condition failing — including
    there being no candidates at all — is ambiguous: the caller must not
    pick one on its own.
    """

    #: Below this confidence, even an unopposed top candidate is too weak
    #: to accept automatically (this is where a lone PARTIAL match — the
    #: weakest tier — typically lands).
    MIN_CONFIDENCE = 0.6
    #: The top candidate must beat the runner-up by at least this much
    #: confidence, or the two are considered too close to call.
    MIN_MARGIN = 0.1

    def decide(self, candidates: tuple[LinkCandidate, ...]) -> AmbiguityDecision:
        """Decide whether `candidates` (already ranked best first) has a confident winner."""
        if not candidates:
            return AmbiguityDecision(
                is_confident=False,
                reason="No candidate schema object matched this business concept at any tier.",
            )

        top = candidates[0]
        if top.confidence < self.MIN_CONFIDENCE:
            return AmbiguityDecision(
                is_confident=False,
                reason=(
                    f"Best candidate ({_describe(top)}, confidence {top.confidence:.2f}) is "
                    f"below the minimum {self.MIN_CONFIDENCE:.2f} required to resolve automatically."
                ),
            )

        if len(candidates) > 1:
            runner_up = candidates[1]
            margin = top.confidence - runner_up.confidence
            if margin < self.MIN_MARGIN:
                return AmbiguityDecision(
                    is_confident=False,
                    reason=(
                        f"Top candidates are within {self.MIN_MARGIN:.2f} confidence of each "
                        f"other ({_describe(top)} at {top.confidence:.2f} vs. "
                        f"{_describe(runner_up)} at {runner_up.confidence:.2f}); cannot pick "
                        "one without more context."
                    ),
                )

        return AmbiguityDecision(is_confident=True)
