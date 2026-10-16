"""Matplotlib/seaborn helpers shared by the analyses that draw a single chart.

Each analysis module draws exactly one chart and saves exactly one image.
Matplotlib is imported lazily and with the headless ``Agg`` backend, so the
analyses that only write CSV never pay for it.
"""

from __future__ import annotations

from pathlib import Path

from .common import ensure_output_dir

FIGURE_SIZE = (9, 5.5)

RECENT_MONTHS_NOTE = (
    "Recent months look worse because their commits may not be integrated yet; "
    "latency is bounded by matching.days_after."
)


def new_chart(title: str):
    """Create a figure with ONE axes. Return ``(fig, ax, palette)``."""
    import matplotlib

    matplotlib.use("Agg")  # Headless: write files only.
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("whitegrid")
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    ax.set_title(title, fontsize=13)
    return fig, ax, sns.color_palette("deep")


def format_date_axis(ax) -> None:
    """Concise month/year ticks on the x axis."""
    import matplotlib.dates as mdates

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))


def save_chart(fig, output: Path, note: str | None = None) -> None:
    """Save the figure (format from the suffix), optionally with a footnote, and close it."""
    import matplotlib.pyplot as plt

    if note:
        fig.text(0.5, -0.015, note, ha="center", fontsize=8, color="#555555")
    ensure_output_dir(output.parent)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
