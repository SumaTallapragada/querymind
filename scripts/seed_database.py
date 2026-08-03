"""CLI entry point: run the business simulation and persist it to PostgreSQL.

Wires together the pieces built across Phases 1-4B — `querymind.core.config`
and `querymind.db` for the database connection, `querymind.seeds.config`/
`scenarios` for what to generate, `SeedOrchestrator` to run it, and
`DatasetValidator` to confirm what landed in PostgreSQL is consistent —
without adding any new architecture of its own.

Usage:
    uv run python scripts/seed_database.py
    uv run python scripts/seed_database.py --scenario black_friday
    uv run python scripts/seed_database.py --dataset-size medium --seed 7
    uv run python scripts/seed_database.py --config path/to/config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from querymind.core.config import get_settings
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory
from querymind.seeds.config import DatasetSizeConfig, SeedConfig
from querymind.seeds.generator import SeedOrchestrator
from querymind.seeds.persistence import AsyncSessionTransactionRunner
from querymind.seeds.report import DatasetValidator
from querymind.seeds.scenarios import STANDARD_SCENARIOS, ScenarioProfile

#: Convenience row-count presets for `--dataset-size`, scaled down from
#: the Phase 2 §9 defaults (`default`) while keeping the same ratios.
_DATASET_SIZE_PRESETS: dict[str, DatasetSizeConfig] = {
    "small": DatasetSizeConfig(
        customers=200,
        suppliers=15,
        warehouses=3,
        product_categories=30,
        products=150,
        promotions=8,
        orders=600,
        payments=620,
        shipments=550,
        inventory=300,
        product_reviews=250,
        returns=45,
    ),
    "medium": DatasetSizeConfig(
        customers=2_000,
        suppliers=60,
        warehouses=6,
        product_categories=80,
        products=800,
        promotions=25,
        orders=6_000,
        payments=6_200,
        shipments=5_500,
        inventory=3_000,
        product_reviews=2_500,
        returns=450,
    ),
}


def _resolve_scenario(name: str) -> ScenarioProfile | None:
    if name == "default":
        return None
    for scenario in STANDARD_SCENARIOS:
        if scenario.name == name:
            return scenario
    available = ", ".join(scenario.name for scenario in STANDARD_SCENARIOS)
    raise SystemExit(f"Unknown scenario {name!r}. Available: default, {available}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and persist a simulated QueryMind dataset."
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to a SeedConfig YAML file.")
    parser.add_argument("--scenario", type=str, default="default", help="Scenario profile name.")
    parser.add_argument("--seed", type=int, default=None, help="Override the random seed.")
    parser.add_argument("--locale", type=str, default=None, help="Override the Faker locale.")
    parser.add_argument(
        "--currency", type=str, default=None, help="Override the ISO 4217 currency code."
    )
    parser.add_argument(
        "--dataset-size",
        type=str,
        choices=["small", "medium", "default"],
        default="default",
        help="Convenience row-count preset.",
    )
    parser.add_argument(
        "--verbosity", type=str, choices=["quiet", "normal", "verbose"], default=None
    )
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> SeedConfig:
    config = SeedConfig.from_yaml(args.config) if args.config else SeedConfig()
    overrides: dict[str, object] = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.locale is not None:
        overrides["locale"] = args.locale
    if args.currency is not None:
        overrides["currency"] = args.currency
    if args.verbosity is not None:
        overrides["output_verbosity"] = args.verbosity
    if args.dataset_size != "default":
        overrides["dataset_size"] = _DATASET_SIZE_PRESETS[args.dataset_size]
    return config.model_copy(update=overrides) if overrides else config


async def _run(args: argparse.Namespace) -> int:
    config = _build_config(args)
    scenario = _resolve_scenario(args.scenario)
    quiet = config.output_verbosity == "quiet"

    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            runner = AsyncSessionTransactionRunner(session)
            orchestrator = SeedOrchestrator(config, runner, scenario=scenario)

            if not quiet:
                print(
                    f"Generating dataset — scenario={scenario.name if scenario else 'default'!r} seed={config.seed}"
                )
            report = await orchestrator.run()
            if not quiet:
                print(report.summary())

            if not quiet:
                print("\nRunning post-generation validation against PostgreSQL...")
            validation = await DatasetValidator(session).validate()
            if not quiet:
                print(validation.summary())
    finally:
        await engine.dispose()

    return 0 if validation.all_passed else 1


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
