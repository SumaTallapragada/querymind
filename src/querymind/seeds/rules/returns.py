"""Return-eligibility business rules.

Named `returns.py`, not `return.py`: `return` is a reserved Python
keyword, matching the same naming decision already made for
`querymind.models.returns` and `querymind.seeds.returns`.
"""

from __future__ import annotations

from typing import ClassVar

from querymind.models.order import OrderStatus
from querymind.models.returns import ReturnReason, ReturnStatus
from querymind.seeds.rules.base import BaseRules


class ReturnRules(BaseRules):
    """Business rules governing whether a purchased item is returned, and why."""

    #: Business policy: how many days after delivery a return may be requested.
    RETURN_WINDOW_DAYS = 30

    #: Only these order statuses make a return possible at all.
    _RETURN_ELIGIBLE_STATUSES: ClassVar[frozenset[OrderStatus]] = frozenset(
        {OrderStatus.DELIVERED, OrderStatus.RETURNED}
    )

    _RETURN_REASON_WEIGHTS: ClassVar[dict[ReturnReason, float]] = {
        ReturnReason.NO_LONGER_NEEDED: 0.35,
        ReturnReason.DEFECTIVE: 0.25,
        ReturnReason.NOT_AS_DESCRIBED: 0.20,
        ReturnReason.WRONG_ITEM: 0.12,
        ReturnReason.DAMAGED_IN_SHIPPING: 0.06,
        ReturnReason.OTHER: 0.02,
    }

    def is_return_window_open(self, delivered_days_ago: int) -> bool:
        """Whether a return request is still within the policy window."""
        return 0 <= delivered_days_ago <= self.RETURN_WINDOW_DAYS

    def is_eligible_for_return(self, order_status: OrderStatus) -> bool:
        """Decide whether a purchased line item from an order in `order_status` gets returned.

        Draws against `config.return_rate`, but only for orders whose
        status makes a return possible at all — an order can't be
        returned before it's been delivered.
        """
        if order_status not in self._RETURN_ELIGIBLE_STATUSES:
            return False
        return self.rng.random() < self.config.return_rate

    def assign_return_reason(self) -> ReturnReason:
        """Draw a return reason."""
        return self._weighted_pick(self._RETURN_REASON_WEIGHTS)

    #: Status distribution once a return is genuinely possible (window
    #: open and there's a captured payment to refund against).
    _RETURN_STATUS_WEIGHTS: ClassVar[dict[ReturnStatus, float]] = {
        ReturnStatus.REQUESTED: 0.05,
        ReturnStatus.APPROVED: 0.10,
        ReturnStatus.REJECTED: 0.10,
        ReturnStatus.REFUNDED: 0.50,
        ReturnStatus.COMPLETED: 0.25,
    }

    def assign_return_status(self, *, window_open: bool, payment_captured: bool) -> ReturnStatus:
        """Draw a return's current status.

        A return outside its policy window, or against a payment that
        never captured (nothing to refund), is always rejected — refund
        eligibility follows the payment's own outcome
        (`PaymentRules`/`PaymentStatus.CAPTURED`), not an independent
        coin flip.
        """
        if not window_open or not payment_captured:
            return ReturnStatus.REJECTED
        return self._weighted_pick(self._RETURN_STATUS_WEIGHTS)
