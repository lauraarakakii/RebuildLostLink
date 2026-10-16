"""Commits linked to more than one email in the same list."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Find commits linked to more than one email in the same list."""
    return (
        scan_enriched(config, list_name)
        .filter(pl.col("is_match").fill_null(False) & pl.col("best_commit").is_not_null())
        .group_by("list", "best_commit")
        .agg(
            pl.col("commit_date").min().alias("commit_date"),
            pl.len().alias("matched_emails"),
            pl.col("score").mean().alias("mean_score"),
        )
        .filter(pl.col("matched_emails") > 1)
        .sort(
            ["matched_emails", "mean_score", "list", "best_commit"],
            descending=[True, True, False, False],
        )
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "commit_reuse")
