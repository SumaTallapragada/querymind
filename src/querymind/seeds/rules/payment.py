"""Payment success/failure business rules."""

from __future__ import annotations

from typing import ClassVar

from querymind.models.payment import PaymentMethod
from querymind.seeds.rules.base import BaseRules


class PaymentRules(BaseRules):
    """Business rules governing payment method selection and transaction outcomes."""

    _PAYMENT_METHOD_WEIGHTS: ClassVar[dict[PaymentMethod, float]] = {
        PaymentMethod.CREDIT_CARD: 0.55,
        PaymentMethod.DEBIT_CARD: 0.20,
        PaymentMethod.PAYPAL: 0.18,
        PaymentMethod.GIFT_CARD: 0.04,
        PaymentMethod.BANK_TRANSFER: 0.03,
    }

    def assign_payment_method(self) -> PaymentMethod:
        """Draw a payment method."""
        return self._weighted_pick(self._PAYMENT_METHOD_WEIGHTS)

    def payment_succeeds(self) -> bool:
        """Decide whether a payment attempt succeeds.

        Draws against `1 - config.payment_failure_rate` — the Black
        Friday scenario raises `payment_failure_rate` (gateway load under
        traffic), so this returns `False` more often under that profile.
        """
        return self.rng.random() >= self.config.payment_failure_rate

    def retry_count_on_failure(self) -> int:
        """How many additional attempts typically follow one failed payment."""
        return self.rng.randint(0, 2)
