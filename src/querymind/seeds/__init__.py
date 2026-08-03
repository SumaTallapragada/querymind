"""Synthetic data generation framework for the approved Phase 2 schema.

This package defines the *shape* of seeding: reusable generator
infrastructure (`base.py`), generic helpers (`utils.py`), one generator
class per domain table, and an orchestration entry point (`generator.py`)
that fixes the order generators must run in. No fake data is produced and
no database is touched anywhere in this package yet — every `generate()`
method is a documented stub. Wiring generators together and persisting
their output is Phase 4 scope.
"""
