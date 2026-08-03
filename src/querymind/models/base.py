"""Re-export point for the declarative base used by every ORM model.

Model modules import ``Base`` from here rather than from ``querymind.db.base``
directly, so the models package has one canonical import path and the
underlying metadata/naming-convention wiring stays defined in exactly one
place (``db/base.py``, established in Phase 1).
"""

from __future__ import annotations

from querymind.db.base import Base

__all__ = ["Base"]
