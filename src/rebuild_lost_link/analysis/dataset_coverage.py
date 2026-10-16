"""Pipeline coverage versus every source email, per list."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import count_true, write_csv
from .datasets import scan_enriched, scan_original


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Compare all source emails with the matching results via a left join."""
    original = scan_original(config, list_name)
    enriched = scan_enriched(config, list_name).select(
        "list",
        "message_id",
        pl.lit(1).alias("_evaluated"),
        "is_match",
        "is_confident_match",
        "error",
    )
    return (
        original.join(
            enriched,
            on=["list", "message_id"],
            how="left",
        )
        .group_by("list")
        .agg(
            pl.len().alias("source_emails"),
            pl.col("_evaluated").count().alias("evaluated_patches"),
            count_true("is_match").alias("matches"),
            count_true("is_confident_match").alias("confident_matches"),
            pl.col("error").is_not_null().sum().alias("errors"),
        )
        .sort(["confident_matches", "matches", "list"], descending=[True, True, False])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "dataset_coverage")
