"""Measure how patch size relates to matching and integration outcomes."""

from __future__ import annotations

from datetime import datetime

import polars as pl

from ..config import Config
from .common import count_true, write_csv
from .datasets import scan_enriched, scan_original

NAME = "patch_size_outcomes"

# Analytical window: patches submitted between May 2016 and May 2026,
# defined by the email date (not the commit date).
WINDOW_START = datetime(2016, 5, 1)
WINDOW_END = datetime(2026, 6, 1)  # exclusive upper bound


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Summarize match outcomes across content-change size bands."""
    changed_lines = (
        pl.col("code")
        .list.join("\n")
        .str.count_matches(r"(?m)^\+[^+]")
        .add(pl.col("code").list.join("\n").str.count_matches(r"(?m)^-[^-]"))
        .alias("changed_lines")
    )
    size_band = (
        pl.when(pl.col("changed_lines") <= 20)
        .then(pl.lit("small_1_20"))
        .when(pl.col("changed_lines") <= 100)
        .then(pl.lit("medium_21_100"))
        .when(pl.col("changed_lines") <= 500)
        .then(pl.lit("large_101_500"))
        .otherwise(pl.lit("very_large_501_plus"))
        .alias("size_band")
    )
    original = (
        scan_original(config, list_name)
        .select("list", "message_id", "code", "date")
        .filter(pl.col("date") >= WINDOW_START)
        .filter(pl.col("date") < WINDOW_END)
        .filter(pl.col("code").list.len() > 0)
        .unique(subset=["list", "message_id"], keep="first")
        .with_columns(changed_lines)
        .with_columns(size_band)
    )
    enriched = scan_enriched(config, list_name).select(
        "list",
        "message_id",
        pl.lit(1).alias("_evaluated"),
        "is_match",
        "is_confident_match",
        "score",
    )
    return (
        original.join(enriched, on=["list", "message_id"], how="left")
        .group_by("list", "size_band")
        .agg(
            pl.len().alias("source_patches"),
            pl.col("changed_lines").median().alias("median_changed_lines"),
            pl.col("_evaluated").count().alias("evaluated_patches"),
            count_true("is_match").alias("matches"),
            count_true("is_confident_match").alias("confident_matches"),
            pl.col("score").mean().alias("mean_score"),
        )
        .with_columns(
            pl.when(pl.col("evaluated_patches") > 0)
            .then(pl.col("matches") / pl.col("evaluated_patches"))
            .otherwise(None)
            .alias("match_rate"),
            pl.when(pl.col("evaluated_patches") > 0)
            .then(pl.col("confident_matches") / pl.col("evaluated_patches"))
            .otherwise(None)
            .alias("confident_match_rate"),
        )
        .sort(["list", "median_changed_lines"])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, NAME)