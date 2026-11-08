"""Pipeline coverage, score distribution and match-quality indicators."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .data import count_true, scan_matches, scan_source


def coverage(config: Config, lists: str) -> pl.LazyFrame:
    matches = scan_matches(config, lists).select(
        "list",
        "message_id",
        pl.lit(1).alias("_evaluated"),
        "best_commit",
        "score",
        "is_match",
        "is_confident_match",
        "error",
    )
    return (
        scan_source(config, lists)
        .select("list", "message_id")
        .join(matches, on=["list", "message_id"], how="left")
        .group_by("list")
        .agg(
            pl.len().alias("source_emails"),
            pl.col("_evaluated").count().alias("evaluated_patches"),
            count_true("is_match").alias("matches"),
            count_true("is_confident_match").alias("confident_matches"),
            (pl.col("_evaluated").is_not_null() & pl.col("score").is_null())
            .sum()
            .alias("without_candidate"),
            (pl.col("score").is_not_null() & ~pl.col("is_match").fill_null(False))
            .sum()
            .alias("below_threshold"),
            pl.col("error").is_not_null().sum().alias("errors"),
            pl.col("score").mean().alias("mean_score"),
        )
        .sort("confident_matches", "list", descending=[True, False])
    )


def score_bands(config: Config, lists: str) -> pl.LazyFrame:
    band = (
        pl.when(pl.col("is_confident_match").fill_null(False))
        .then(pl.lit("confident_match"))
        .when(pl.col("is_match").fill_null(False))
        .then(pl.lit("review_match"))
        .when(pl.col("score").is_null())
        .then(pl.lit("no_candidate"))
        .otherwise(pl.lit("below_threshold"))
        .alias("result_band")
    )
    return (
        scan_matches(config, lists)
        .with_columns(band)
        .group_by("list", "result_band")
        .agg(
            pl.len().alias("patches"),
            pl.col("score").mean().alias("mean_score"),
            pl.col("score").min().alias("min_score"),
            pl.col("score").max().alias("max_score"),
        )
        .sort("list", "result_band")
    )


def match_errors(config: Config, lists: str) -> pl.LazyFrame:
    return (
        scan_matches(config, lists)
        .filter(pl.col("error").is_not_null())
        .group_by("list", "error")
        .agg(pl.len().alias("occurrences"))
        .sort("occurrences", "list", "error", descending=[True, False, False])
    )


def commit_reuse(config: Config, lists: str) -> pl.LazyFrame:
    return (
        scan_matches(config, lists)
        .filter(pl.col("is_match").fill_null(False) & pl.col("best_commit").is_not_null())
        .group_by("list", "best_commit")
        .agg(pl.len().alias("matched_emails"), pl.col("score").mean().alias("mean_score"))
        .filter(pl.col("matched_emails") > 1)
        .sort("matched_emails", "mean_score", "list", descending=[True, True, False])
    )
