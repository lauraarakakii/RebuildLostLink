"""Step ``enrich``: persist the match CSVs as partitioned Parquet."""

from __future__ import annotations

from ..config import Config
from ..enrich import run


def main(config: Config) -> None:
    """Write ``list=<name>/data.parquet`` under ``paths.enriched_root``."""
    run(config)
