"""ORM domain models for the Phase 2 approved schema.

Importing this package registers every model module's tables on
``Base.metadata`` — this is what lets Alembic's autogenerate (and anything
else that needs the full schema) see the whole picture from a single
``import querymind.models``, without every caller needing to know the full
list of model modules.
"""

from querymind.models import customer as customer
from querymind.models import inventory as inventory
from querymind.models import order as order
from querymind.models import payment as payment
from querymind.models import product as product
from querymind.models import promotion as promotion
from querymind.models import returns as returns
from querymind.models import review as review
from querymind.models import shipment as shipment
from querymind.models import supplier as supplier
