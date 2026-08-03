"""Shipment generator (feeds Phase 2 §3.11 `shipments`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import ClassVar

from querymind.models.inventory import Warehouse
from querymind.models.order import Order, OrderStatus
from querymind.models.shipment import Shipment, ShipmentStatus
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.rules.shipment import ShipmentRules


class ShipmentGenerator(BaseGenerator[Shipment]):
    """Generates `Shipment` records for already-generated orders and warehouses.

    Consumes `ShipmentRules` for carrier assignment, shipment status, and
    processing/transit delays — this generator makes no such decision
    itself, beyond reconciling the drawn status against the parent
    order's `order_status` so the two can never contradict each other
    (e.g. a `DELIVERED` order can't have an `IN_TRANSIT` shipment).

    Only orders whose `order_status` implies payment succeeded
    (confirmed/shipped/delivered/returned) get a shipment at all — a
    `PENDING` or `CANCELLED` order was never fulfilled, matching Payments
    before Shipment in the temporal-integrity requirements.
    """

    #: Order statuses that imply the order was actually fulfilled and so
    #: gets a shipment.
    _SHIPPABLE_STATUSES: ClassVar[frozenset[OrderStatus]] = frozenset(
        {OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    )

    def __init__(
        self,
        count: int,
        orders: Sequence[Order],
        warehouses: Sequence[Warehouse],
        context: SeedContext | None = None,
        *,
        rules: ShipmentRules,
    ) -> None:
        super().__init__(count, context)
        self.orders = orders
        self.warehouses = warehouses
        self.rules = rules
        self._tracking_sequence = 0

    def generate(self) -> list[Shipment]:
        if not self.warehouses:
            raise ValueError("ShipmentGenerator requires at least one warehouse")

        shipments: list[Shipment] = []
        for order in self.orders:
            if order.order_status not in self._SHIPPABLE_STATUSES:
                continue
            shipments.append(self._build(order))
        return shipments

    def _build(self, order: Order) -> Shipment:
        status = self._resolve_status(order.order_status)
        carrier = self.rules.assign_carrier()

        shipped_at: datetime | None = None
        delivered_at: datetime | None = None
        if status != ShipmentStatus.PENDING:
            shipped_at = order.order_date + timedelta(days=self.rules.processing_delay_days())
        if status == ShipmentStatus.DELIVERED:
            delivered_at = (shipped_at or order.order_date) + timedelta(
                days=self.rules.transit_delay_days(carrier)
            )

        self._tracking_sequence += 1
        shipment = Shipment(
            carrier=carrier,
            tracking_number=f"1Z{self.context.seed:04d}{self._tracking_sequence:010d}",
            shipment_status=status,
            shipped_at=shipped_at,
            delivered_at=delivered_at,
        )
        shipment.order = order
        shipment.warehouse = self.rng.choice(self.warehouses)
        return shipment

    def _resolve_status(self, order_status: OrderStatus) -> ShipmentStatus:
        """Reconcile a `ShipmentRules`-drawn status against `order_status`.

        A delivered/returned order's shipment must itself be `DELIVERED`
        — there's no other consistent outcome. For orders still in
        flight (confirmed/shipped), the drawn status is used as-is unless
        it would claim more progress than the order itself has made yet.
        """
        if order_status in (OrderStatus.DELIVERED, OrderStatus.RETURNED):
            return ShipmentStatus.DELIVERED

        drawn = self.rules.assign_shipment_status()
        if order_status == OrderStatus.CONFIRMED:
            return (
                drawn
                if drawn in (ShipmentStatus.PENDING, ShipmentStatus.FAILED)
                else ShipmentStatus.PENDING
            )
        # order_status == OrderStatus.SHIPPED
        return drawn if drawn != ShipmentStatus.DELIVERED else ShipmentStatus.IN_TRANSIT
