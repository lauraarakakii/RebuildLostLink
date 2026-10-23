"""Create comparison figures from a ``patch_size_outcomes.csv`` export.

The source report is already aggregated by mailing list and patch-size band, so
these charts deliberately describe matching coverage rather than integration
latency.  Use the temporal analyses when per-month behaviour is needed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import BoundaryNorm, ListedColormap

SIZE_BANDS = ("small_1_20", "medium_21_100", "large_101_500", "very_large_501_plus")
SIZE_LABELS = ("1–20", "21–100", "101–500", "501+")
PRIMARY_LISTS = ("amd-gfx", "linux-iio", "alsa-devel")
SECONDARY_LISTS = ("bpf", "linux-scsi", "linux-mm")
ALL_LISTS = (*PRIMARY_LISTS, *SECONDARY_LISTS, "linux-arm-kernel")
DISPLAY_NAMES = {"linux-iio": "iio", "linux-arm-kernel": "linux-arm-kernel"}


def display_name(list_name: str) -> str:
    """Use the familiar short name where the dataset has a Linux prefix."""
    return DISPLAY_NAMES.get(list_name, list_name)


def filtered(frame: pl.DataFrame, names: tuple[str, ...]) -> pl.DataFrame:
    """Keep requested lists in their semantic size-band order."""
    return (
        frame.filter(pl.col("list").is_in(names))
        .with_columns(pl.col("size_band").cast(pl.Enum(SIZE_BANDS)).alias("size_band"))
        .sort("list", "size_band")
    )


def save(fig, path: Path) -> None:
    """Persist one SVG figure and release its Matplotlib resources."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_confident_rate_lines(
    frame: pl.DataFrame, names: tuple[str, ...], output: Path, title: str
) -> None:
    """Compare confident-match rates across the four size bands."""
    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    palette = sns.color_palette("deep", n_colors=len(names))
    values = filtered(frame, names)
    for color, list_name in zip(palette, names, strict=True):
        rows = values.filter(pl.col("list") == list_name)
        if rows.is_empty():
            continue
        label = display_name(list_name)
        x = range(len(SIZE_BANDS))
        ax.plot(
            x,
            rows["confident_match_rate"],
            marker="o",
            color=color,
            label=label,
        )
    ax.set_title(title)
    ax.set_xlabel("Changed lines in patch")
    ax.set_ylabel("Confident match rate")
    ax.set_xticks(range(len(SIZE_BANDS)), SIZE_LABELS)
    ax.yaxis.set_major_formatter("{x:.0%}")
    ax.set_ylim(0, 1)
    ax.legend(title="Mailing list")
    sns.despine(ax=ax)
    save(fig, output)


def plot_heatmap(frame: pl.DataFrame, output: Path) -> None:
    """Show match-rate patterns for the selected high-volume lists."""
    values = filtered(frame, ALL_LISTS)
    matrix = (
        values.select("list", "size_band", "match_rate")
        .pivot(on="size_band", index="list", values="match_rate")
        .select("list", *SIZE_BANDS)
    )
    ordered_names = [name for name in ALL_LISTS if name in matrix["list"].to_list()]
    matrix = matrix.with_columns(pl.col("list").cast(pl.Enum(ordered_names))).sort("list")
    fig, ax = plt.subplots(figsize=(8.5, 5.5), constrained_layout=True)
    boundaries = [step / 100 for step in range(50, 86, 5)]
    cmap = ListedColormap(sns.color_palette("YlGnBu", n_colors=len(boundaries) - 1))
    norm = BoundaryNorm(boundaries, cmap.N, clip=True)
    sns.heatmap(
        matrix.select(*SIZE_BANDS).to_numpy(),
        annot=True,
        fmt=".0%",
        cmap=cmap,
        norm=norm,
        xticklabels=SIZE_LABELS,
        yticklabels=[display_name(name) for name in matrix["list"].to_list()],
        cbar_kws={"label": "Match rate", "ticks": boundaries[::2]},
        ax=ax,
    )
    ax.set_title("Match rate by patch size (5 percentage-point color steps)")
    ax.set_xlabel("Changed lines in patch")
    ax.set_ylabel("Mailing list")
    save(fig, output)


def plot_scatter(frame: pl.DataFrame, output: Path) -> None:
    """Relate patch size to coverage while encoding the evaluated volume."""
    values = filtered(frame, ALL_LISTS)
    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    palette = sns.color_palette("deep", n_colors=len(ALL_LISTS))
    for color, list_name in zip(palette, ALL_LISTS, strict=True):
        rows = values.filter(pl.col("list") == list_name)
        if rows.is_empty():
            continue
        ax.scatter(
            rows["median_changed_lines"],
            rows["match_rate"],
            s=(rows["evaluated_patches"] ** 0.5).to_list(),
            color=color,
            alpha=0.65,
            label=display_name(list_name),
        )
    ax.set_xscale("log")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter("{x:.0%}")
    ax.set_title("Coverage by patch size and evaluated volume")
    ax.set_xlabel("Median changed lines (logarithmic scale)")
    ax.set_ylabel("Match rate")
    ax.legend(title="Mailing list", ncol=2, fontsize=8)
    sns.despine(ax=ax)
    save(fig, output)


def main() -> None:
    """Parse command-line arguments and create the comparison figures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="patch_size_outcomes.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("output/patch-size-visuals"))
    args = parser.parse_args()

    frame = pl.read_csv(args.input)
    plot_confident_rate_lines(
        frame,
        PRIMARY_LISTS,
        args.output_dir / "patch_size_confident_rates.svg",
        "Confident match rate by patch size",
    )
    plot_heatmap(frame, args.output_dir / "patch_size_heatmap.svg")
    plot_scatter(frame, args.output_dir / "patch_size_scatter.svg")


if __name__ == "__main__":
    main()
