"""Chart: patches per month (by email date), evaluated vs. matched.

One analysis, one chart. Outputs in ``output_dir``: ``patches_per_month.svg``
and ``patches_per_month.csv`` (the data behind the chart).
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

NAME = "patches_per_month"


def plot(monthly: pl.DataFrame, output: Path, title: str, confident_only: bool = False) -> None:
    """Draw the bar chart and save it to ``output`` (format from the suffix)."""
    fig, ax, palette = new_chart(title)
    kind = "confident matches" if confident_only else "matches"
    matched_col = "confident_matches" if confident_only else "matches"
    months = monthly["month"].to_list()

    ax.bar(
        months,
        monthly["evaluated_patches"].to_list(),
        width=25,
        color=palette[0],
        alpha=0.35,
        label=f"Evaluated (n={monthly['evaluated_patches'].sum()})",
    )
    ax.bar(
        months,
        monthly[matched_col].to_list(),
        width=25,
        color=palette[0],
        label=f"{kind.capitalize()} (n={monthly[matched_col].sum()})",
    )
    ax.set_ylabel("Patches")
    ax.legend()
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
    write_csv(
        monthly.select("month", "evaluated_patches", "matches", "confident_matches"),
        output_dir,
        NAME,
    )
    figure = Path(output_dir) / f"{NAME}.svg"
    plot(
        monthly,
        figure,
        title=f"Patches per Month (by Email Date) - list: {list_name}",
        confident_only=confident_only,
    )
    logger.info("Saved figure to %s", figure)
