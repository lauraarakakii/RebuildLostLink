"""Candidate coverage and match quality, per list."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import count_true, write_csv
from .datasets import scan_enriched


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Summarize candidate coverage and match quality by list."""
    return (
        scan_enriched(config, list_name)
        .group_by("list")
        .agg(
            pl.len().alias("evaluated_patches"),
            count_true("is_match").alias("matches"),
            count_true("is_confident_match").alias("confident_matches"),
            pl.col("best_commit").is_null().sum().alias("without_candidate"),
            pl.col("error").is_not_null().sum().alias("errors"),
            pl.col("score").mean().alias("mean_score"),
        )
        .sort(["confident_matches", "matches", "list"], descending=[True, True, False])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "match_coverage")
