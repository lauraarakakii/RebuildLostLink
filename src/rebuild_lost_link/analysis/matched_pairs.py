"""Focused integration analysis for amd-gfx, iio, and alsa-devel.

The analysis is deliberately limited to submissions dated from May 2016 through
May 2026. It keeps the matched-pair table for reproducibility and produces
three complementary figures: monthly volume, a per-list latency CDF, and an
adapted Cartesian quadrant plot. In the latter, the horizontal split is the
midpoint of the study period and the vertical split is the observed median
integration period: ``P. menores`` are below that median and ``P. maiores``
are at or above it.
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
FOCUS_LISTS = ("amd-gfx", "iio", "alsa-devel")
START = datetime(2016, 5, 1)
END = datetime(2026, 6, 1)
PERIOD_MIDPOINT = datetime(2021, 5, 1)
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


def plot_monthly(monthly: pl.DataFrame, output: Path) -> None:
    """Draw matched-patch volume over time for the three lists."""
    fig, ax, palette = new_chart("Patches com match por mês (maio/2016–maio/2026)")
    for index, list_label in enumerate(FOCUS_LISTS):
        values = monthly.filter(pl.col("list") == list_label)
        if not values.is_empty():
            ax.plot(
                values["month"].to_list(),
                values["matched_patches"].to_list(),
                color=palette[index],
                label=list_label,
            )
    ax.set_xlabel("Mês de submissão")
    ax.set_ylabel("Patches com match")
    ax.legend(title="Lista")
    format_date_axis(ax)
    save_chart(fig, output, NOTE)


def plot_latency_cdf(pairs: pl.DataFrame, output: Path) -> None:
    """Draw empirical integration-time CDFs, one line per mailing list."""
    fig, ax, palette = new_chart("Período de integração por lista")
    for index, list_label in enumerate(FOCUS_LISTS):
        values = pairs.filter(pl.col("list") == list_label).sort("latency_days")
        if values.is_empty():
            continue
        share = [(rank + 1) / values.height for rank in range(values.height)]
        ax.step(
            values["latency_days"].to_list(),
            share,
            where="post",
            color=palette[index],
            label=f"{list_label} (n={values.height})",
        )
    ax.set_xlabel("Período de integração (dias)")
    ax.set_ylabel("Proporção acumulada de patches com match")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter("{x:.0%}")
    ax.legend(title="Lista")
    save_chart(fig, output, NOTE)


def plot_quadrants(pairs: pl.DataFrame, output: Path) -> None:
    """Draw the requested Cartesian plane for shorter and longer periods."""
    fig, ax, palette = new_chart("Plano cartesiano dos períodos de integração")
    median_latency = pairs["latency_days"].median()
    assert median_latency is not None

    for index, list_label in enumerate(FOCUS_LISTS):
        values = pairs.filter(pl.col("list") == list_label)
        if not values.is_empty():
            ax.scatter(
                values["email_date"].to_list(),
                values["latency_days"].to_list(),
                color=palette[index],
                alpha=0.5,
                s=18,
                label=list_label,
            )

    ax.axvline(PERIOD_MIDPOINT, color="black", linewidth=1)
    ax.axhline(median_latency, color="black", linewidth=1)
    ax.set_xlabel("Data de submissão (período inicial ← → período final)")
    ax.set_ylabel("Período de integração (dias)")
    ax.annotate("P. maiores", (START, median_latency), xytext=(8, 8), textcoords="offset points")
    ax.annotate("P. menores", (START, median_latency), xytext=(8, -16), textcoords="offset points")
    ax.text(
        PERIOD_MIDPOINT,
        median_latency,
        f"mediana = {median_latency:.1f} dias",
        ha="left",
        va="bottom",
        fontsize=8,
    )
    ax.legend(title="Lista")
    format_date_axis(ax)
    save_chart(fig, output, NOTE)


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    """Write the focused table, monthly summary, and its three figures."""
    pairs = build(config, list_name).collect()
    write_csv(pairs, output_dir, NAME)
    monthly = monthly_summary(pairs.lazy()).collect()
    write_csv(monthly, output_dir, f"{NAME}_monthly")
    if pairs.is_empty():
        logger.warning(
            "No matched pairs for %s between May 2016 and May 2026; skipping figures.",
            ", ".join(FOCUS_LISTS),
        )
        return

    output = Path(output_dir)
    plot_monthly(monthly, output / f"{NAME}_monthly.svg")
    plot_latency_cdf(pairs, output / f"{NAME}_latency_cdf.svg")
    plot_quadrants(pairs, output / f"{NAME}_quadrants.svg")
    logger.info("Saved focused matched-pairs figures to %s", output)
