"""Focused integration analysis for amd-gfx, iio, alsa-devel, and linux-scsi.

The analysis is deliberately limited to submissions dated from May 2016 through
May 2026. It keeps the matched-pair table for reproducibility and produces
three complementary figures: a biweekly volume zoom, a per-list latency CDF,
and an adapted Cartesian quadrant plot. In the latter, the horizontal split is
the midpoint of the study period and the vertical split is the observed median
integration period.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched, scan_original
from .plotting import format_date_axis, new_chart, save_chart

logger = logging.getLogger(__name__)

NAME = "matched_pairs"
# ``linux-iio`` is the canonical partition name in the MLH-derived output.
FOCUS_LISTS = ("amd-gfx", "linux-iio", "alsa-devel", "linux-scsi")
START = datetime(2016, 5, 1)
END = datetime(2026, 6, 1)
PERIOD_MIDPOINT = datetime(2021, 5, 1)
ZOOM_START = datetime(2024, 1, 1)
ZOOM_END = datetime(2026, 1, 1)
MAX_QUADRANT_POINTS_PER_LIST = 5_000
NOTE = (
    "Only matched patches submitted from May 2016 through May 2026 are shown; "
    "latency is commit date minus email date."
)


def _commit_date() -> pl.Expr:
    """Normalize native and ISO-8601 commit timestamps to naive UTC."""
    return (
        pl.col("commit_date")
        .cast(pl.Utf8)
        .str.to_datetime(time_unit="us", time_zone="UTC", strict=False)
        .dt.replace_time_zone(None)
        .alias("commit_date")
    )


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Return in-window matched pairs from the three study mailing lists.

    ``list_name`` can narrow the study set (for example, ``"iio"``), but it
    can never broaden it beyond :data:`FOCUS_LISTS`.
    """
    return (
        scan_enriched(config, list_name)
        .filter(pl.col("list").is_in(FOCUS_LISTS))
        .with_columns(_commit_date())
        .filter(pl.col("is_match").fill_null(False) & pl.col("commit_date").is_not_null())
        .join(
            scan_original(config, list_name)
            .filter(pl.col("list").is_in(FOCUS_LISTS))
            .select("list", "message_id", pl.col("date").alias("email_date"))
            .unique(subset=["list", "message_id"], keep="first"),
            on=["list", "message_id"],
            how="inner",
        )
        .filter((pl.col("email_date") >= START) & (pl.col("email_date") < END))
        .with_columns(
            ((pl.col("commit_date") - pl.col("email_date")).dt.total_seconds() / 86400).alias(
                "latency_days"
            )
        )
        .select(
            "list",
            "message_id",
            "email_date",
            "commit_date",
            "latency_days",
            "best_commit",
            "score",
            "is_confident_match",
        )
        .sort(["list", "email_date", "score"], descending=[False, False, True])
    )


def monthly_summary(pairs: pl.LazyFrame) -> pl.LazyFrame:
    """Summarize matched submissions by list and email month."""
    return (
        pairs.with_columns(pl.col("email_date").dt.truncate("1mo").alias("month"))
        .group_by("list", "month")
        .agg(
            pl.len().alias("matched_patches"),
            pl.col("latency_days").median().alias("latency_median_days"),
            pl.col("latency_days").quantile(0.25).alias("latency_p25_days"),
            pl.col("latency_days").quantile(0.75).alias("latency_p75_days"),
        )
        .sort("list", "month")
    )


def biweekly_summary(pairs: pl.LazyFrame) -> pl.LazyFrame:
    """Count matched patches per two-week interval in the two full recent years."""
    return (
        pairs.filter((pl.col("email_date") >= ZOOM_START) & (pl.col("email_date") < ZOOM_END))
        .with_columns(pl.col("email_date").dt.truncate("2w").alias("period"))
        .group_by("list", "period")
        .agg(pl.len().alias("matched_patches"))
        .sort("list", "period")
    )


def plot_biweekly(biweekly: pl.DataFrame, output: Path) -> None:
    """Zoom into 2024–2025 with biweekly matched-patch counts."""
    fig, ax, palette = new_chart("Matched patches per fortnight (2024–2025)")
    for index, list_label in enumerate(FOCUS_LISTS):
        values = biweekly.filter(pl.col("list") == list_label)
        if not values.is_empty():
            ax.plot(
                values["period"].to_list(),
                values["matched_patches"].to_list(),
                color=palette[index],
                label=list_label,
            )
    ax.set_xlabel("Patch email date (Date: header)")
    ax.set_ylabel("Matched patches")
    ax.legend(title="Mailing list")
    format_date_axis(ax)
    save_chart(
        fig,
        output,
        "Uses the original Date: email timestamp; Git author dates can be rewritten during merges.",
    )


def plot_latency_cdf(pairs: pl.DataFrame, output: Path) -> None:
    """Draw latency CDFs on a base-10 logarithmic day axis.

    The log axis starts at one day. Earlier (and rare negative) observations
    are grouped at that first tick, retaining their contribution to the CDF
    while keeping ticks in intuitive day, ten-day, and hundred-day units.
    """
    fig, ax, palette = new_chart("Integration latency by mailing list")
    for index, list_label in enumerate(FOCUS_LISTS):
        values = (
            pairs.filter(pl.col("list") == list_label)
            .with_columns(pl.col("latency_days").clip(lower_bound=1).alias("latency_for_plot"))
            .sort("latency_for_plot")
        )
        if values.is_empty():
            continue
        share = [(rank + 1) / values.height for rank in range(values.height)]
        ax.step(
            values["latency_for_plot"].to_list(),
            share,
            where="post",
            color=palette[index],
            label=f"{list_label} (n={values.height})",
        )
    ax.set_xscale("log", base=10)
    ax.set_xlabel("Integration latency (days, logarithmic scale)")
    ax.set_ylabel("Cumulative share of matched patches")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter("{x:.0%}")
    ax.legend(title="Mailing list")
    save_chart(
        fig,
        output,
        "Latency is mainline commit date minus the patch email Date: timestamp; "
        "all observations of one day or less are grouped at the one-day tick.",
    )


def plot_quadrants(pairs: pl.DataFrame, output: Path) -> None:
    """Draw the Cartesian plane with a symmetric logarithmic latency axis.

    ``symlog`` preserves the rare zero/negative latencies allowed by the
    candidate window while revealing the dense cluster of short integrations
    and the long-tail cases in the same plot.
    """
    fig, ax, palette = new_chart("Integration latency quadrants (logarithmic scale)")
    median_latency = pairs["latency_days"].median()
    assert median_latency is not None

    for index, list_label in enumerate(FOCUS_LISTS):
        values = pairs.filter(pl.col("list") == list_label)
        if not values.is_empty():
            plotted = values.sample(n=min(values.height, MAX_QUADRANT_POINTS_PER_LIST), seed=index)
            ax.scatter(
                plotted["email_date"].to_list(),
                plotted["latency_days"].to_list(),
                color=palette[index],
                alpha=0.28,
                s=10,
                label=(
                    list_label
                    if values.height <= MAX_QUADRANT_POINTS_PER_LIST
                    else f"{list_label} (sample of {MAX_QUADRANT_POINTS_PER_LIST:,})"
                ),
                zorder=2,
            )

    ax.axvline(PERIOD_MIDPOINT, color="black", linewidth=1, linestyle="--", zorder=1)
    ax.axhline(median_latency, color="black", linewidth=1, linestyle="--", zorder=1)
    ax.set_yscale("symlog", linthresh=1, linscale=0.8)
    ax.set_xlabel("Patch email date (early period ← → late period)")
    ax.set_ylabel("Integration latency (days, symmetric logarithmic scale)")
    ax.text(
        0.02,
        0.97,
        "Longer periods",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        weight="medium",
    )
    ax.text(
        0.02,
        0.03,
        "Shorter periods",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        weight="medium",
    )
    ax.text(
        PERIOD_MIDPOINT,
        median_latency,
        f"median = {median_latency:.1f} days",
        ha="left",
        va="bottom",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
    )
    ax.legend(title="Mailing list")
    format_date_axis(ax)
    save_chart(fig, output, NOTE)


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    """Write the focused table, summaries, and its three figures."""
    pairs = build(config, list_name).collect()
    write_csv(pairs, output_dir, NAME)
    monthly = monthly_summary(pairs.lazy()).collect()
    write_csv(monthly, output_dir, f"{NAME}_monthly")
    biweekly = biweekly_summary(pairs.lazy()).collect()
    write_csv(biweekly, output_dir, f"{NAME}_biweekly")
    if pairs.is_empty():
        logger.warning(
            "No matched pairs for %s between May 2016 and May 2026; skipping figures.",
            ", ".join(FOCUS_LISTS),
        )
        return

    output = Path(output_dir)
    plot_biweekly(biweekly, output / f"{NAME}_biweekly.svg")
    plot_latency_cdf(pairs, output / f"{NAME}_latency_cdf.svg")
    plot_quadrants(pairs, output / f"{NAME}_quadrants.svg")
    logger.info("Saved focused matched-pairs figures to %s", output)
