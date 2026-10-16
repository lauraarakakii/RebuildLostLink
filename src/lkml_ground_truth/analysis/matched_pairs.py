"""Matched email/commit pairs with both dates, for review."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched, scan_original


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Return matched email/commit pairs with both dates for review."""
    return (
        scan_enriched(config, list_name)
        .filter(pl.col("is_match").fill_null(False) & pl.col("commit_date").is_not_null())
        .join(
            scan_original(config, list_name).select(
                "list", "message_id", pl.col("date").alias("email_date")
            ),
            on=["list", "message_id"],
            how="inner",
        )
        .select(
            "list",
            "message_id",
            "email_date",
            "commit_date",
            "best_commit",
            "score",
            "is_confident_match",
        )
        .sort(["list", "email_date", "score"], descending=[False, False, True])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "matched_pairs")
