"""The repair loop's stopping condition and terminal-status logic.

`RepairStrategy` is the single place that decides "try again or stop,
and why" — kept entirely separate from `SQLRepairEngine`, which only
calls it, so the engine's own loop stays pure orchestration with no
embedded decision logic (per the architecture notes: "Engine
orchestrates only... Keep every component single responsibility").
"""

from __future__ import annotations

from querymind.sql_repair.exceptions import SQLRepairConfigurationError
from querymind.sql_repair.models import RepairAttempt, RepairStatus

#: Default number of repair attempts before giving up.
DEFAULT_MAX_ATTEMPTS = 3


class RepairStrategy:
    """Decides whether the repair loop should keep going, and what its final status is.

    Stops after `max_attempts` attempts, or earlier if two consecutive
    attempts report the exact same set of validation error codes — that
    signals the LLM's repair isn't changing anything meaningful, so
    burning the remaining attempts on identical output would not help.
    """

    def __init__(self, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        if max_attempts < 1:
            raise SQLRepairConfigurationError(f"max_attempts must be >= 1, got {max_attempts!r}.")
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_continue(self, history: tuple[RepairAttempt, ...]) -> bool:
        """Whether another repair attempt should be made, given the (failed) attempts so far."""
        if not history or history[-1].success:
            return False
        if len(history) >= self._max_attempts:
            return False
        return len(history) < 2 or self._made_progress(history[-2], history[-1])

    def final_status(self, history: tuple[RepairAttempt, ...]) -> RepairStatus:
        """The terminal `RepairStatus` for a loop that has just stopped."""
        if not history:
            return RepairStatus.UNREPAIRABLE
        if history[-1].success:
            return RepairStatus.REPAIRED
        if len(history) >= 2 and not self._made_progress(history[-2], history[-1]):
            return RepairStatus.NO_PROGRESS
        if len(history) >= self._max_attempts:
            return RepairStatus.MAX_ATTEMPTS_REACHED
        return RepairStatus.UNREPAIRABLE

    @staticmethod
    def _made_progress(previous: RepairAttempt, current: RepairAttempt) -> bool:
        """Whether `current` reported a different set of error codes than `previous`."""
        previous_codes = {issue.code for issue in previous.validation_result.errors}
        current_codes = {issue.code for issue in current.validation_result.errors}
        return current_codes != previous_codes
