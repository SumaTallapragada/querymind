"""Shipment-timing business rules."""

from __future__ import annotations

from typing import ClassVar

from querymind.models.shipment import ShipmentStatus
from querymind.seeds.rules.base import BaseRules


class ShipmentRules(BaseRules):
    """Business rules governing carrier assignment, timing, and delivery outcomes."""

    _CARRIER_WEIGHTS: ClassVar[dict[str, float]] = {
        "UPS": 0.40,
        "FedEx": 0.35,
        "DHL": 0.15,
        "USPS": 0.10,
    }

    _SHIPMENT_STATUS_WEIGHTS: ClassVar[dict[ShipmentStatus, float]] = {
        ShipmentStatus.DELIVERED: 0.80,
        ShipmentStatus.IN_TRANSIT: 0.12,
        ShipmentStatus.PENDING: 0.05,
        ShipmentStatus.FAILED: 0.02,
        ShipmentStatus.RETURNED_TO_SENDER: 0.01,
    }

    #: Carriers modeled as faster/more reliable transit.
    _FAST_CARRIERS: ClassVar[frozenset[str]] = frozenset({"FedEx", "UPS"})

    def assign_carrier(self) -> str:
        """Draw a shipping carrier."""
        return self._weighted_pick(self._CARRIER_WEIGHTS)

    def assign_shipment_status(self) -> ShipmentStatus:
        """Draw a shipment's current status."""
        return self._weighted_pick(self._SHIPMENT_STATUS_WEIGHTS)

    def processing_delay_days(self) -> int:
        """Days between order confirmation and the parcel leaving the warehouse."""
        return self.rng.randint(0, 2)

    def transit_delay_days(self, carrier: str) -> int:
        """Days in transit for `carrier` — expedited carriers are modeled faster."""
        low, high = (1, 3) if carrier in self._FAST_CARRIERS else (3, 7)
        return self.rng.randint(low, high)
