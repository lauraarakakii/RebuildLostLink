"""Compare integration outcomes for initial and threaded patch submissions."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import count_true, write_csv
from .datasets import scan_enriched, scan_original

NAME = "discussion_context"


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Summarize match outcomes by whether a patch is part of a discussion thread."""
    original = (
        scan_original(config, list_name)
        .select("list", "message_id", "code", "in_reply_to", "references")
        .filter(pl.col("code").list.len() > 0)
        .unique(subset=["list", "message_id"], keep="first")
        .with_columns(
            pl.when(pl.col("in_reply_to").is_not_null() | (pl.col("references").list.len() > 0))
            .then(pl.lit("reply_or_revision"))
            .otherwise(pl.lit("initial_submission"))
            .alias("discussion_context")
        )
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
        .group_by("list", "discussion_context")
        .agg(
            pl.len().alias("source_patches"),
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
        .sort(["list", "discussion_context"])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, NAME)
