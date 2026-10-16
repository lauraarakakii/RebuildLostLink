"""Temporal analysis of the matching results: volume, match rate and latency.

Patches are grouped by the month of the email date. Two questions are answered:

* How many patches were evaluated and matched to a commit, and at what rate?
* How long does a patch take to be integrated (``commit_date - email_date``)?

Data wrangling uses Polars LazyFrames over the ``original`` and ``enriched``
datasets; seaborn/Matplotlib only draw the figure. Outputs, in ``output_dir``:
``temporal.svg`` (figure) and ``temporal.csv`` (monthly summary).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from ..config import Config
from .common import ensure_output_dir, write_csv
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


def matched_latency(
    config: Config, list_name: str, confident_only: bool = False
) -> pl.LazyFrame:
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


def plot(
    monthly: pl.DataFrame,
    latency: pl.Series,
    output: Path,
    title: str,
    confident_only: bool = False,
) -> None:
    """Draw the 2x2 figure and save it to ``output`` (format from the suffix)."""
    import matplotlib

    matplotlib.use("Agg")  # Headless: write files only.
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("whitegrid")

    months = monthly["month"].to_list()
    kind = "confident matches" if confident_only else "matches"
    matched_col = "confident_matches" if confident_only else "matches"
    palette = sns.color_palette("deep")

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    (ax_vol, ax_rate), (ax_hist, ax_lat) = axes

    # (1) Monthly volume: evaluated patches vs. matched patches.
    ax_vol.bar(
        months,
        monthly["evaluated_patches"].to_list(),
        width=25,
        color=palette[0],
        alpha=0.35,
        label=f"Evaluated (n={monthly['evaluated_patches'].sum()})",
    )
    ax_vol.bar(
        months,
        monthly[matched_col].to_list(),
        width=25,
        color=palette[0],
        label=f"{kind.capitalize()} (n={monthly[matched_col].sum()})",
    )
    ax_vol.set_title("Patches per Month (by Email Date)")
    ax_vol.set_ylabel("Patches")
    ax_vol.legend()

    # (2) Monthly match rate.
    sns.lineplot(
        x=months, y=(monthly["match_rate"] * 100).to_list(), ax=ax_rate, label="Matches"
    )
    sns.lineplot(
        x=months,
        y=(monthly["confident_match_rate"] * 100).to_list(),
        ax=ax_rate,
        label="Confident matches",
    )
    ax_rate.set_title("Match Rate per Month")
    ax_rate.set_ylabel("% of evaluated patches")
    ax_rate.set_ylim(0, 100)

    # (3) Distribution of integration latency (clipped at the 99th percentile).
    if latency.len() > 0:
        upper = latency.quantile(0.99)
        median = latency.median()
        sns.histplot(latency.filter(latency <= upper).to_numpy(), bins=60, ax=ax_hist)
        ax_hist.axvline(
            median, color=palette[1], linestyle="--", label=f"Median: {median:.1f} days"
        )
        ax_hist.legend()
    ax_hist.set_title(f"Integration Latency ({kind}, n={latency.len()}; up to P99)")
    ax_hist.set_xlabel("Days from email to commit")
    ax_hist.set_ylabel("Patches")

    # (4) Median latency per month with the interquartile range.
    lat = monthly.filter(pl.col("latency_median").is_not_null())
    lat_months = lat["month"].to_list()
    ax_lat.fill_between(
        lat_months,
        lat["latency_p25"].to_list(),
        lat["latency_p75"].to_list(),
        color=palette[0],
        alpha=0.25,
        label="Interquartile range",
    )
    sns.lineplot(x=lat_months, y=lat["latency_median"].to_list(), ax=ax_lat, label="Median")
    ax_lat.set_title("Integration Latency per Month")
    ax_lat.set_ylabel("Days from email to commit")
    ax_lat.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.95)

    for ax in (ax_vol, ax_rate, ax_lat):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))

    fig.suptitle(title, fontsize=14)
    fig.text(
        0.5,
        -0.015,
        "Recent months look worse because their commits may not be integrated yet; "
        "latency is bounded by matching.days_after.",
        ha="center",
        fontsize=8,
        color="#555555",
    )
    ensure_output_dir(output.parent)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def main(
    config: Config,
    output_dir: str,
    list_name: str = "all",
    confident_only: bool = False,
) -> None:
    monthly = build(config, list_name, confident_only).collect()
    if monthly.is_empty():
        logger.warning("No evaluated patches with an email date were found; nothing to plot.")
        return
    latency = (
        matched_latency(config, list_name, confident_only)
        .select("latency_days")
        .collect()
        .to_series()
    )

    write_csv(monthly, output_dir, "temporal")
    figure = Path(output_dir) / "temporal.svg"
    plot(
        monthly,
        latency,
        figure,
        title=f"Temporal Analysis - list: {list_name}",
        confident_only=confident_only,
    )
    logger.info("Saved figure to %s", figure)
