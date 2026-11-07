"""Enrichment: persist the match CSVs as Parquet partitioned by mailing list."""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from .config import Config

logger = logging.getLogger(__name__)


def enrich_list(config: Config, list_name: str) -> None:
    """Write ``list=<name>/data.parquet`` from the list's match CSV.

    ``commit_date`` (ISO 8601 with UTC offset in the CSV) becomes a timezone-free
    UTC ``timestamp[us]`` so it can be compared with email dates.
    """
    matches_path = Path(config.paths.resolved_output_path(list_name))
    output_path = Path(config.paths.enriched_parquet_path(list_name))
    if not matches_path.exists():
        raise FileNotFoundError(
            f"Match CSV not found for list '{list_name}': {matches_path}. "
            "Run the matching step first."
        )

    matches = pl.read_csv(matches_path).with_columns(
        pl.col("commit_date")
        .cast(pl.Utf8)
        .str.to_datetime(time_unit="us", time_zone="UTC", strict=False)
        .dt.replace_time_zone(None)
    )
    logger.info(
        "%s: %d rows (%d with a commit)",
        list_name,
        matches.height,
        matches["best_commit"].is_not_null().sum(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    matches.write_parquet(output_path)


def run(config: Config) -> None:
    list_name = config.paths.list_name
    if list_name.lower() not in ("all", "*"):
        enrich_list(config, list_name)
        return
    available = config.paths.available_output_lists()
    if not available:
        logger.warning("No match CSVs found at '%s'.", config.paths.output_path)
    for name in available:
        enrich_list(config, name)
