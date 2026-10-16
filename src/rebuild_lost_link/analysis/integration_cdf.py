"""Chart: empirical cumulative distribution of integration latency.

The CDF answers research questions such as "what fraction of linked patches is
integrated within 7, 30, or 90 days?" without assuming a parametric latency
distribution. It writes both one chart and the points behind it so results can
be reproduced or compared across mailing lists.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from ..config import Config
from .common import write_csv
from .plotting import new_chart, save_chart
from .temporal_data import matched_latency

logger = logging.getLogger(__name__)

NAME = "integration_cdf"
NOTE = "Conditional on patches linked to a commit; latency is bounded by " "matching.days_after."


def build(config: Config, list_name: str, confident_only: bool = False) -> pl.LazyFrame:
    """Return sorted latencies and their empirical cumulative proportion."""
    return (
        matched_latency(config, list_name, confident_only)
        .select("latency_days")
        .sort("latency_days")
        .with_row_index("rank", offset=1)
        .with_columns((pl.col("rank") / pl.len()).alias("integrated_share"))
        .select("latency_days", "integrated_share")
    )


def plot(cdf: pl.DataFrame, output: Path, title: str) -> None:
    """Draw the empirical CDF as a one-axes step chart."""
    fig, ax, palette = new_chart(title)
    ax.step(
        cdf["latency_days"].to_list(),
        cdf["integrated_share"].to_list(),
        where="post",
        color=palette[0],
    )
    ax.set_xlabel("Days from email to commit")
    ax.set_ylabel("Share of linked patches integrated")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter("{x:.0%}")
    save_chart(fig, output, NOTE)


def main(
    config: Config,
    output_dir: str,
    list_name: str = "all",
    confident_only: bool = False,
) -> None:
    cdf = build(config, list_name, confident_only).collect()
    if cdf.is_empty():
        logger.warning("No matched patches with a commit date were found; nothing to plot.")
        return
    write_csv(cdf, output_dir, NAME)
    figure = Path(output_dir) / f"{NAME}.svg"
    kind = "confident matches" if confident_only else "matches"
    plot(
        cdf,
        figure,
        title=f"Cumulative Integration Time ({kind}, n={cdf.height}) - list: {list_name}",
    )
    logger.info("Saved figure to %s", figure)
