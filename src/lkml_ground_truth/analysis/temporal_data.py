"""Shared data layer of the temporal analyses (no plotting here).

Patches are grouped by the month of the email date. The four temporal analyses
each draw ONE chart from these frames:

* ``patches_per_month``    - evaluated vs. matched patches per month
* ``match_rate_per_month`` - share of evaluated patches matched per month
* ``latency_distribution`` - histogram of ``commit_date - email_date``
* ``latency_per_month``    - monthly median and interquartile range of latency

Data wrangling uses Polars LazyFrames over the ``original`` and ``enriched``
datasets.
"""

from __future__ import annotations

import logging

import polars as pl

from ..config import Config
from .datasets import scan_enriched, scan_original

logger = logging.getLogger(__name__)


def evaluated_patches(config: Config, list_name: str) -> pl.LazyFrame:
    """Every evaluated patch with its email date and (UTC) commit date.

    ``commit_date`` is stored as an ISO 8601 string with a UTC offset. Both
    dates become naive UTC datetimes so they can be subtracted.
    ``latency_days`` is only set for rows with a commit date, and can be
    slightly negative because the matching window starts ``days_before`` days
    before the email date.
    """
    enriched = scan_enriched(config, list_name).select(
        "list",
        "message_id",
        "score",
        pl.col("is_match").fill_null(False),
        pl.col("is_confident_match").fill_null(False),
        pl.col("commit_date")
        .str.to_datetime(time_zone="UTC", strict=False)
        .dt.replace_time_zone(None)
        .alias("commit_date"),
    )
    original = (
        scan_original(config, list_name)
        .select("list", "message_id", pl.col("date").alias("email_date"))
        .filter(pl.col("email_date").is_not_null())
        .unique(subset=["list", "message_id"], keep="first")
    )
    return enriched.join(original, on=["list", "message_id"], how="inner").with_columns(
        ((pl.col("commit_date") - pl.col("email_date")).dt.total_seconds() / 86400).alias(
            "latency_days"
        )
    )


def matched_latency(config: Config, list_name: str, confident_only: bool = False) -> pl.LazyFrame:
    """Matched patches with a known integration latency, in days."""
    flag = "is_confident_match" if confident_only else "is_match"
    return evaluated_patches(config, list_name).filter(
        pl.col(flag) & pl.col("latency_days").is_not_null()
    )


def build(config: Config, list_name: str, confident_only: bool = False) -> pl.LazyFrame:
    """One row per month of email date: volumes, match rates and latency quartiles."""
    flag = "is_confident_match" if confident_only else "is_match"
    return (
        evaluated_patches(config, list_name)
        .with_columns(pl.col("email_date").dt.truncate("1mo").alias("month"))
        .group_by("month")
        .agg(
            pl.len().alias("evaluated_patches"),
            pl.col("is_match").sum().alias("matches"),
            pl.col("is_confident_match").sum().alias("confident_matches"),
            pl.col("latency_days").filter(pl.col(flag)).quantile(0.25).alias("latency_p25"),
            pl.col("latency_days").filter(pl.col(flag)).median().alias("latency_median"),
            pl.col("latency_days").filter(pl.col(flag)).quantile(0.75).alias("latency_p75"),
        )
        .with_columns(
            (pl.col("matches") / pl.col("evaluated_patches")).alias("match_rate"),
            (pl.col("confident_matches") / pl.col("evaluated_patches")).alias(
                "confident_match_rate"
            ),
        )
        .sort("month")
    )


def load_monthly(
    config: Config, list_name: str, confident_only: bool = False
) -> pl.DataFrame | None:
    """Collect :func:`build`; log a warning and return ``None`` when it is empty."""
    monthly = build(config, list_name, confident_only).collect()
    if monthly.is_empty():
        logger.warning("No evaluated patches with an email date were found; nothing to plot.")
        return None
    return monthly
