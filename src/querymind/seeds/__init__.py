"""Synthetic data generation framework for the approved Phase 2 schema.

Reusable generator infrastructure (`base.py`), generic helpers
(`utils.py`), one generator class per domain table, business-consistency
rules (`rules/`), and an orchestration entry point
(`generator.py::SeedOrchestrator`) that runs every generator in a fixed
dependency order and persists each stage's output through a
`TransactionRunner` (`persistence.py::AsyncSessionTransactionRunner`)
before the next stage begins. `scripts/seed_database.py` is the CLI
entry point that wires this package to a real database connection — see
`docs/getting-started.md`.
"""
