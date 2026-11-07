"""How patch size, and optionally sender type, relates to matching outcomes."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .data import STUDY_END, STUDY_START, count_true, rate, scan_matches, scan_source

SIZE_BANDS = ("small_1_20", "medium_21_100", "large_101_500", "very_large_501_plus")

VENDOR_DOMAIN = "amd.com"
THIRD_PARTY_DOMAINS = [
    "igalia.com", "collabora.com", "redhat.com", "suse.de", "linaro.org",
    "huawei.com", "oracle.com", "linux.microsoft.com", "oss.qualcomm.com", "arm.com",
]  # fmt: skip
INFRA_DOMAINS = ["kernel.org", "linux.dev", "infradead.org"]

_PATCH_TEXT = pl.col("code").list.join("\n")
_CHANGED_LINES = _PATCH_TEXT.str.count_matches(r"(?m)^\+[^+]") + _PATCH_TEXT.str.count_matches(
    r"(?m)^-[^-]"
)
_SIZE_BAND = (
    pl.when(pl.col("changed_lines") <= 20)
    .then(pl.lit(SIZE_BANDS[0]))
    .when(pl.col("changed_lines") <= 100)
    .then(pl.lit(SIZE_BANDS[1]))
    .when(pl.col("changed_lines") <= 500)
    .then(pl.lit(SIZE_BANDS[2]))
    .otherwise(pl.lit(SIZE_BANDS[3]))
)
_SENDER_DOMAIN = (
    pl.when(pl.col("from").str.contains("<"))
    .then(pl.col("from").str.extract(r"<([^>]+)>", 1))
    .otherwise(pl.col("from").str.strip_chars())
    .str.to_lowercase()
    .str.split("@")
    .list.last()
)
_SENDER_TYPE = (
    pl.when(pl.col("sender_domain") == VENDOR_DOMAIN)
    .then(pl.lit("vendor"))
    .when(pl.col("sender_domain").is_in(THIRD_PARTY_DOMAINS))
    .then(pl.lit("third_party"))
    .when(pl.col("sender_domain").is_in(INFRA_DOMAINS))
    .then(pl.lit("infrastructure"))
    .otherwise(pl.lit("community"))
)


def _outcomes(config: Config, lists: str, by_sender: bool) -> pl.LazyFrame:
    keys = ["list", "size_band"] + (["sender_type"] if by_sender else [])
    source = (
        scan_source(config, lists)
        .select("list", "message_id", "code", "date", "from")
        .filter(pl.col("date").is_between(STUDY_START, STUDY_END, closed="left"))
        .filter(pl.col("code").list.len() > 0)
        .unique(subset=["list", "message_id"], keep="first")
        .with_columns(_CHANGED_LINES.alias("changed_lines"))
        .with_columns(_SIZE_BAND.alias("size_band"), _SENDER_DOMAIN.alias("sender_domain"))
        .with_columns(_SENDER_TYPE.alias("sender_type"))
    )
    matches = scan_matches(config, lists).select(
        "list",
        "message_id",
        pl.lit(1).alias("_evaluated"),
        "is_match",
        "is_confident_match",
        "score",
    )
    return (
        source.join(matches, on=["list", "message_id"], how="left")
        .group_by(keys)
        .agg(
            pl.len().alias("source_patches"),
            pl.col("changed_lines").median().alias("median_changed_lines"),
            pl.col("_evaluated").count().alias("evaluated_patches"),
            count_true("is_match").alias("matches"),
            count_true("is_confident_match").alias("confident_matches"),
            pl.col("score").mean().alias("mean_score"),
        )
        .with_columns(
            rate("matches", "evaluated_patches").alias("match_rate"),
            rate("confident_matches", "evaluated_patches").alias("confident_match_rate"),
        )
        .sort(*keys[:1], *keys[2:], "median_changed_lines")
    )


def patch_size_outcomes(config: Config, lists: str) -> pl.LazyFrame:
    return _outcomes(config, lists, by_sender=False)


def patch_size_outcomes_by_sender(config: Config, lists: str) -> pl.LazyFrame:
    return _outcomes(config, lists, by_sender=True)
