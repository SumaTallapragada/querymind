"""Return generator (feeds Phase 2 §3.14 `returns`).

Named `returns.py`, not `return.py`: `return` is a reserved Python
keyword, matching the same naming decision already made for
`querymind.models.returns` and `querymind.seeds.rules.returns`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import ClassVar

from querymind.models.order import OrderItem
from querymind.models.payment import Payment, PaymentStatus
from querymind.models.returns import Return, ReturnStatus
from querymind.models.shipment import Shipment
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.rules.returns import ReturnRules
from querymind.seeds.utils import round_currency


class ReturnGenerator(BaseGenerator[Return]):
    """Generates `Return` records for already-generated, delivered order items.

    Consumes `ReturnRules` for eligibility, the window/refund-gated
    status draw, and the return reason — this generator makes no such
    decision itself. `requested_at` is always computed from that order's
    real shipment `delivered_at`, so a return can never be generated
    before the order it belongs to was delivered.

    `refund_amount` is only set when the resulting status is `REFUNDED`
    or `COMPLETED` *and* the order's payment actually captured — refunds
    only ever follow a real captured payment, matching "refund
    eligibility follows PaymentRules".

    `shipments` and `payments` are new required dependencies beyond the
    original Phase 3 signature: delivery timing and payment-capture
    status can't be known without them.
    """

    #: Statuses that represent the return request having been resolved
    #: one way or another (vs. still open/pending).
    _TERMINAL_STATUSES: ClassVar[frozenset[ReturnStatus]] = frozenset(
        {
            ReturnStatus.APPROVED,
            ReturnStatus.REJECTED,
            ReturnStatus.REFUNDED,
            ReturnStatus.COMPLETED,
        }
    )
    #: Statuses that imply money actually moved back to the customer.
    _REFUNDABLE_STATUSES: ClassVar[frozenset[ReturnStatus]] = frozenset(
        {ReturnStatus.REFUNDED, ReturnStatus.COMPLETED}
    )

    def __init__(
        self,
        count: int,
        order_items: Sequence[OrderItem],
        context: SeedContext | None = None,
        *,
        shipments: Sequence[Shipment],
        payments: Sequence[Payment],
        rules: ReturnRules,
    ) -> None:
        super().__init__(count, context)
        self.order_items = order_items
        self.shipments = shipments
        self.payments = payments
        self.rules = rules

    def generate(self) -> list[Return]:
        delivered_at_by_order = self._delivered_at_by_order()
        captured_by_order = self._captured_by_order()

        returns: list[Return] = []
        for item in self.order_items:
            order = item.order
            delivered_at = delivered_at_by_order.get(id(order))
            if delivered_at is None:
                continue
            if not self.rules.is_eligible_for_return(order.order_status):
                continue

            requested_at = delivered_at + timedelta(
                days=self.rng.randint(1, self.rules.RETURN_WINDOW_DAYS + 10)
            )
            window_open = self.rules.is_return_window_open((requested_at - delivered_at).days)
            payment_captured = captured_by_order.get(id(order), False)

            status = self.rules.assign_return_status(
                window_open=window_open, payment_captured=payment_captured
            )
            quantity_returned = self.rng.randint(1, item.quantity)
            resolved_at = (
                requested_at + timedelta(days=self.rng.randint(1, 10))
                if status in self._TERMINAL_STATUSES
                else None
            )
            refund_amount = (
                round_currency(item.unit_price * quantity_returned)
                if status in self._REFUNDABLE_STATUSES
                else None
            )

            return_record = Return(
                return_reason=self.rules.assign_return_reason(),
                return_status=status,
                quantity_returned=quantity_returned,
                refund_amount=refund_amount,
                requested_at=requested_at,
                resolved_at=resolved_at,
            )
            return_record.order_item = item
            returns.append(return_record)

        return returns

    def _delivered_at_by_order(self) -> dict[int, datetime]:
        delivered_at: dict[int, datetime] = {}
        for shipment in self.shipments:
            if shipment.delivered_at is None:
                continue
            key = id(shipment.order)
            existing = delivered_at.get(key)
            if existing is None or shipment.delivered_at > existing:
                delivered_at[key] = shipment.delivered_at
        return delivered_at

    def _captured_by_order(self) -> dict[int, bool]:
        captured: dict[int, bool] = {}
        for payment in self.payments:
            key = id(payment.order)
            if payment.payment_status == PaymentStatus.CAPTURED:
                captured[key] = True
            else:
                captured.setdefault(key, False)
        return captured
