"""Chart: match rate per month (by email date).

One analysis, one chart. Outputs in ``output_dir``: ``match_rate_per_month.svg``
and ``match_rate_per_month.csv`` (the data behind the chart).
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

NAME = "match_rate_per_month"


def plot(monthly: pl.DataFrame, output: Path, title: str) -> None:
    """Draw the line chart and save it to ``output`` (format from the suffix)."""
    import seaborn as sns

    fig, ax, _ = new_chart(title)
    months = monthly["month"].to_list()

    sns.lineplot(x=months, y=(monthly["match_rate"] * 100).to_list(), ax=ax, label="Matches")
    sns.lineplot(
        x=months,
        y=(monthly["confident_match_rate"] * 100).to_list(),
        ax=ax,
        label="Confident matches",
    )
    ax.set_ylabel("% of evaluated patches")
    ax.set_ylim(0, 100)
    format_date_axis(ax)
    save_chart(fig, output, RECENT_MONTHS_NOTE)


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    monthly = load_monthly(config, list_name)
    if monthly is None:
        return
    write_csv(monthly.select("month", "match_rate", "confident_match_rate"), output_dir, NAME)
    figure = Path(output_dir) / f"{NAME}.svg"
    plot(monthly, figure, title=f"Match Rate per Month - list: {list_name}")
    logger.info("Saved figure to %s", figure)
