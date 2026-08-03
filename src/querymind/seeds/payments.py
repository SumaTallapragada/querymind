"""Payment generator (feeds Phase 2 §3.10 `payments`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import ClassVar

from querymind.models.order import Order, OrderStatus
from querymind.models.payment import Payment, PaymentMethod, PaymentStatus
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.rules.payment import PaymentRules


class PaymentGenerator(BaseGenerator[Payment]):
    """Generates `Payment` records for already-generated orders.

    Consumes `PaymentRules` for method assignment, success/failure draws,
    and retry counts — this generator makes no such decision itself.

    An order's payment history is anchored to its `order_status`: orders
    that progressed to confirmed/shipped/delivered/returned always end
    with a `CAPTURED` payment (they couldn't have progressed otherwise —
    temporal/business consistency overrides a run of unlucky failure
    draws); a `CANCELLED` order's payment never successfully captures; a
    `PENDING` order's single payment is still mid-flight. Failed attempts
    before an eventual capture are their own `FAILED` rows, per
    `PaymentRules.retry_count_on_failure`. `amount` always equals
    `order.total_amount` — a payment attempt is for the whole order, and
    every attempt (failed or not) charges the same amount.

    Because the real payment count depends on how many orders needed
    retries — a business-realistic, not independently controllable,
    quantity — this generator's returned length is the natural result of
    that process, not forced to exactly match `count` (the same
    trade-off `OrderItemGenerator` makes, for the same reason).
    """

    #: Order statuses that imply the order's payment ultimately succeeded.
    _SUCCESSFUL_STATUSES: ClassVar[frozenset[OrderStatus]] = frozenset(
        {OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    )

    def __init__(
        self,
        count: int,
        orders: Sequence[Order],
        context: SeedContext | None = None,
        *,
        rules: PaymentRules,
    ) -> None:
        super().__init__(count, context)
        self.orders = orders
        self.rules = rules
        self._reference_sequence = 0

    def generate(self) -> list[Payment]:
        payments: list[Payment] = []
        for order in self.orders:
            payments.extend(self._payments_for_order(order))
        return payments

    def _payments_for_order(self, order: Order) -> list[Payment]:
        if order.order_status == OrderStatus.PENDING:
            return [
                self._build(order, self.rules.assign_payment_method(), PaymentStatus.PENDING, None)
            ]

        must_succeed = order.order_status in self._SUCCESSFUL_STATUSES
        is_cancelled = order.order_status == OrderStatus.CANCELLED
        payment_method = self.rules.assign_payment_method()
        attempts: list[Payment] = []

        succeeded = self._draw_success(is_cancelled)
        retries_remaining = self.rules.retry_count_on_failure() if not succeeded else 0
        while not succeeded and retries_remaining > 0:
            attempts.append(self._build(order, payment_method, PaymentStatus.FAILED, None))
            retries_remaining -= 1
            succeeded = self._draw_success(is_cancelled)

        if succeeded or must_succeed:
            paid_at = order.order_date + timedelta(minutes=self.rng.randint(1, 180))
            attempts.append(self._build(order, payment_method, PaymentStatus.CAPTURED, paid_at))
        else:
            attempts.append(self._build(order, payment_method, PaymentStatus.FAILED, None))

        return attempts

    def _draw_success(self, is_cancelled: bool) -> bool:
        """`PaymentRules.payment_succeeds()`, narrowed for cancelled orders.

        Most cancellations stem from a payment that never went through; a
        smaller share are cancelled *after* a successful charge (customer
        changed their mind, fraud review, ...). Still genuinely defers to
        `PaymentRules` for the base success draw — this only adds an
        extra, documented gate on top for the cancelled-order case.
        """
        succeeded = self.rules.payment_succeeds()
        if is_cancelled and succeeded:
            succeeded = self.rng.random() < 0.3
        return succeeded

    def _build(
        self,
        order: Order,
        payment_method: PaymentMethod,
        payment_status: PaymentStatus,
        paid_at: datetime | None,
    ) -> Payment:
        self._reference_sequence += 1
        payment = Payment(
            payment_method=payment_method,
            payment_status=payment_status,
            amount=order.total_amount,
            transaction_reference=f"ch_{self.context.seed:04d}{self._reference_sequence:08d}",
            paid_at=paid_at,
        )
        payment.order = order
        return payment
