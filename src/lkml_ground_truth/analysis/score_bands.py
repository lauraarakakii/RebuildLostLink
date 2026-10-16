"""Patches grouped by the decision already made by the matcher."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Group patches by the decision already made by the matcher."""
    band = (
        pl.when(pl.col("is_confident_match").fill_null(False))
        .then(pl.lit("confident_match"))
        .when(pl.col("is_match").fill_null(False))
        .then(pl.lit("review_match"))
        .when(pl.col("best_commit").is_null())
        .then(pl.lit("no_candidate"))
        .otherwise(pl.lit("below_threshold"))
        .alias("result_band")
    )
    return (
        scan_enriched(config, list_name)
        .with_columns(band)
        .group_by("list", "result_band")
        .agg(
            pl.len().alias("patches"),
            pl.col("score").mean().alias("mean_score"),
            pl.col("score").min().alias("min_score"),
            pl.col("score").max().alias("max_score"),
        )
        .sort(["list", "result_band"])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "score_bands")
