"""Integration latency (``commit_date - email_date``) of matched patches."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .data import scan_matches, scan_source

WITHIN_DAYS = (7, 30, 90)


def integration_latency(config: Config, lists: str) -> pl.LazyFrame:
    matches = (
        scan_matches(config, lists)
        .filter(pl.col("is_match").fill_null(False))
        .select(
            "list",
            "message_id",
            pl.col("commit_date")
            .cast(pl.Utf8)
            .str.to_datetime(time_unit="us", time_zone="UTC", strict=False)
            .dt.replace_time_zone(None)
            .alias("commit_date"),
        )
    )
    source = (
        scan_source(config, lists)
        .select("list", "message_id", pl.col("date").alias("email_date"))
        .unique(subset=["list", "message_id"], keep="first")
    )
    latency = pl.col("latency_days")
    return (
        matches.join(source, on=["list", "message_id"])
        .with_columns(
            ((pl.col("commit_date") - pl.col("email_date")).dt.total_seconds() / 86400).alias(
                "latency_days"
            )
        )
        .filter(latency.is_not_null())
        .group_by("list")
        .agg(
            pl.len().alias("matched_patches"),
            latency.quantile(0.25).alias("p25_days"),
            latency.median().alias("median_days"),
            latency.quantile(0.75).alias("p75_days"),
            *((latency <= days).mean().alias(f"share_within_{days}d") for days in WITHIN_DAYS),
        )
        .sort("list")
    )
