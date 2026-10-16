"""Chart: distribution of the integration latency (``commit_date - email_date``).

One analysis, one chart. Output in ``output_dir``: ``latency_distribution.svg``.
The values are clipped at the 99th percentile so outliers do not flatten the
histogram. The underlying per-patch latencies are available through the
``matched_pairs`` analysis.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from ..config import Config
from .plotting import RECENT_MONTHS_NOTE, new_chart, save_chart
from .temporal_data import matched_latency

logger = logging.getLogger(__name__)

NAME = "latency_distribution"


def plot(latency: pl.Series, output: Path, title: str) -> None:
    """Draw the histogram (up to P99, with the median) and save it to ``output``."""
    import seaborn as sns

    fig, ax, palette = new_chart(title)
    upper = latency.quantile(0.99)
    median = latency.median()

    sns.histplot(latency.filter(latency <= upper).to_numpy(), bins=60, ax=ax)
    ax.axvline(median, color=palette[1], linestyle="--", label=f"Median: {median:.1f} days")
    ax.set_xlabel("Days from email to commit")
    ax.set_ylabel("Patches")
    ax.legend()
    save_chart(fig, output, RECENT_MONTHS_NOTE)


def main(
    config: Config,
    output_dir: str,
    list_name: str = "all",
    confident_only: bool = False,
) -> None:
    latency = (
        matched_latency(config, list_name, confident_only)
        .select("latency_days")
        .collect()
        .to_series()
    )
    if latency.len() == 0:
        logger.warning("No matched patches with a commit date were found; nothing to plot.")
        return
    kind = "confident matches" if confident_only else "matches"
    figure = Path(output_dir) / f"{NAME}.svg"
    plot(
        latency,
        figure,
        title=f"Integration Latency ({kind}, n={latency.len()}; up to P99) - list: {list_name}",
    )
    logger.info("Saved figure to %s", figure)
