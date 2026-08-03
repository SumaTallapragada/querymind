"""Shared SQLAlchemy declarative base.

Every ORM model in every future domain module inherits from this single
``Base`` so that:

* Alembic's autogeneration can discover all models from one
  ``Base.metadata`` regardless of which package they live in.
* Constraint and index names follow one naming convention across the whole
  schema, which is what makes Alembic autogenerate reliably detect and
  name diffs (unnamed constraints otherwise get opaque, database-assigned
  names that differ between environments).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit naming convention for constraints/indexes. Without this, Postgres
# assigns auto-generated names that are not reproducible across
# environments, which breaks Alembic's ability to generate stable
# downgrade/upgrade migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
