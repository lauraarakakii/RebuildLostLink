"""Chart: median integration latency per month, with the interquartile range.

One analysis, one chart. Outputs in ``output_dir``: ``latency_per_month.svg``
and ``latency_per_month.csv`` (the data behind the chart).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from ..config import Config
from .common import write_csv
from .plotting import RECENT_MONTHS_NOTE, format_date_axis, new_chart, save_chart
from .temporal_data import load_monthly

logger = logging.getLogger(__name__)

NAME = "latency_per_month"


def plot(monthly: pl.DataFrame, output: Path, title: str) -> None:
    """Draw the median line with the P25-P75 band and save it to ``output``."""
    import seaborn as sns

    fig, ax, palette = new_chart(title)
    months = monthly["month"].to_list()

    ax.fill_between(
        months,
        monthly["latency_p25"].to_list(),
        monthly["latency_p75"].to_list(),
        color=palette[0],
        alpha=0.25,
        label="Interquartile range",
    )
    sns.lineplot(x=months, y=monthly["latency_median"].to_list(), ax=ax, label="Median")
    ax.set_ylabel("Days from email to commit")
    ax.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.95)
    format_date_axis(ax)
    save_chart(fig, output, RECENT_MONTHS_NOTE)


def main(
    config: Config,
    output_dir: str,
    list_name: str = "all",
    confident_only: bool = False,
) -> None:
    monthly = load_monthly(config, list_name, confident_only)
    if monthly is None:
        return
    latency = monthly.filter(pl.col("latency_median").is_not_null()).select(
        "month", "latency_p25", "latency_median", "latency_p75"
    )
    if latency.is_empty():
        logger.warning("No matched patches with a commit date were found; nothing to plot.")
        return
    write_csv(latency, output_dir, NAME)
    figure = Path(output_dir) / f"{NAME}.svg"
    kind = "confident matches" if confident_only else "matches"
    plot(latency, figure, title=f"Integration Latency per Month ({kind}) - list: {list_name}")
    logger.info("Saved figure to %s", figure)
