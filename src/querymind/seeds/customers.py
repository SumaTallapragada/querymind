"""Customer domain generators (feeds Phase 2 §3.1-3.2).

Mirrors `querymind.models.customer`, which holds both `Customer` and
`CustomerAddress` — the address generator stays alongside the customer
generator, matching the models' own grouping.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from querymind.models.customer import AddressType, Customer, CustomerAddress
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.rules.customer import CustomerRules
from querymind.seeds.utils import create_faker, random_date_between, weighted_choice


class CustomerGenerator(BaseGenerator[Customer]):
    """Generates standalone `Customer` records.

    Consumes `CustomerRules` for segment, signup-channel, and active-flag
    assignment — this generator makes no such decision itself.
    """

    #: Self-described gender distribution — `customers.gender` is
    #: nullable, and a meaningful share of real signups decline to state it.
    _GENDER_WEIGHTS: ClassVar[dict[str | None, float]] = {
        "female": 0.42,
        "male": 0.42,
        "non-binary": 0.03,
        None: 0.13,
    }

    def __init__(
        self,
        count: int,
        config: SeedConfig,
        rules: CustomerRules,
        context: SeedContext | None = None,
    ) -> None:
        super().__init__(count, context)
        self.config = config
        self.rules = rules
        self._faker = create_faker(self.context.seed, config.locale)

    def generate(self) -> list[Customer]:
        genders = list(self._GENDER_WEIGHTS.keys())
        gender_weights = list(self._GENDER_WEIGHTS.values())

        customers: list[Customer] = []
        for index in range(1, self.count + 1):
            signup_date = random_date_between(
                self.rng, self.config.business_start_date, self.config.business_end_date
            )
            customers.append(
                Customer(
                    customer_number=f"CUST-{index:08d}",
                    first_name=self._faker.first_name(),
                    last_name=self._faker.last_name(),
                    email=self._faker.unique.email(),
                    phone=self._faker.phone_number(),
                    date_of_birth=self._faker.date_of_birth(minimum_age=18, maximum_age=85),
                    gender=weighted_choice(self.rng, genders, gender_weights),
                    customer_segment=self.rules.assign_segment(),
                    signup_date=signup_date,
                    signup_channel=self.rules.assign_signup_channel(),
                    is_active=self.rules.is_active(signup_date, self.config.business_end_date),
                )
            )
        return customers


class CustomerAddressGenerator(BaseGenerator[CustomerAddress]):
    """Generates `CustomerAddress` records for already-generated customers.

    Depends on customers (`customer_addresses.customer_id` is a `NOT NULL`
    foreign key), linked via the ORM `customer` relationship since
    customers aren't persisted yet at generation time.

    Every customer gets one default shipping address first; any remaining
    `count` beyond `len(customers)` is distributed as extra addresses
    (a second shipping address, a separate billing address, ...) —
    matching the ~1.4 addresses/customer average in Phase 2 §9.
    """

    def __init__(
        self,
        count: int,
        customers: Sequence[Customer],
        config: SeedConfig,
        context: SeedContext | None = None,
    ) -> None:
        super().__init__(count, context)
        self.customers = customers
        self.config = config
        self._faker = create_faker(self.context.seed, config.locale)

    def generate(self) -> list[CustomerAddress]:
        if not self.customers:
            raise ValueError("CustomerAddressGenerator requires at least one customer")

        # Tracks which (customer, address_type) pairs already have a
        # default address, so we never emit a second one — the schema's
        # partial unique index (customer_id, address_type) WHERE
        # is_default forbids it.
        default_seen: set[tuple[int, AddressType]] = set()
        address_types = list(AddressType)

        addresses: list[CustomerAddress] = []
        base_count = min(self.count, len(self.customers))
        for customer in self.customers[:base_count]:
            addresses.append(self._build_address(customer, AddressType.SHIPPING, is_default=True))
            default_seen.add((id(customer), AddressType.SHIPPING))

        remaining = self.count - base_count
        while remaining > 0:
            customer = self.rng.choice(self.customers)
            address_type = self.rng.choice(address_types)
            key = (id(customer), address_type)
            is_default = key not in default_seen
            if is_default:
                default_seen.add(key)
            addresses.append(self._build_address(customer, address_type, is_default=is_default))
            remaining -= 1

        return addresses

    def _build_address(
        self, customer: Customer, address_type: AddressType, *, is_default: bool
    ) -> CustomerAddress:
        address = CustomerAddress(
            address_type=address_type,
            is_default=is_default,
            line1=self._faker.street_address(),
            line2=self._faker.secondary_address() if self.rng.random() < 0.25 else None,
            city=self._faker.city(),
            state_province=self._faker.state_abbr(include_territories=False),
            postal_code=self._faker.postcode(),
            country_code="US",
        )
        address.customer = customer
        return address
