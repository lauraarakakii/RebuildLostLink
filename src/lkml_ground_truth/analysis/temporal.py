"""Temporal analysis of the matching results, with a Matplotlib figure.

Two questions are answered, both over time (by month of the patch email date):

* How many patches were evaluated and matched to a commit, and at what rate?
* How long does a patch take to be integrated (``commit_date - email_date``)?

The data wrangling is done with Polars LazyFrames over the ``original`` and
``enriched`` datasets; Matplotlib is only used to draw the figure.

Usage (from the repository root)::

    make analysis ANALYSIS=temporal LIST=all
    uv run python -m lkml_ground_truth.analysis.temporal --config config.toml --list netdev
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from ..config import Config, load_config
from .datasets import scan_enriched, scan_original

DEFAULT_OUTPUT = "output/analysis/temporal.png"


def evaluated_patches(config: Config, list_name: str) -> pl.LazyFrame:
    """Every evaluated patch with its email date and (UTC) commit date.

    ``score`` is stored as text in the enriched dataset and ``commit_date`` as
    an ISO 8601 string with a UTC offset, so both are normalized here. Dates are
    naive UTC datetimes so they can be subtracted. ``latency_days`` is only set
    for rows that have a commit date; it can be slightly negative because the
    matching window starts ``days_before`` days before the email date.
    """
    enriched = scan_enriched(config, list_name).select(
        "list",
        "message_id",
        pl.col("score").cast(pl.Float64, strict=False),
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


def monthly_activity(
    config: Config, list_name: str, confident_only: bool = False
) -> pl.LazyFrame:
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


def plot_temporal(
    monthly: pl.DataFrame,
    latency: pl.Series,
    output: Path,
    title: str,
    confident_only: bool = False,
    dpi: int = 150,
) -> None:
    """Draw the 2x2 figure and save it to ``output``."""
    import matplotlib

    matplotlib.use("Agg")  # Headless: write files only.
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    months = monthly["month"].to_list()
    kind = "confident matches" if confident_only else "matches"

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    (ax_vol, ax_rate), (ax_hist, ax_lat) = axes

    # (1) Monthly volume: evaluated patches vs. matched patches.
    ax_vol.bar(months, monthly["evaluated_patches"], width=25, color="#c7d3e3", label="Evaluated")
    ax_vol.bar(
        months,
        monthly["confident_matches" if confident_only else "matches"],
        width=25,
        color="#2b6cb0",
        label=kind.capitalize(),
    )
    ax_vol.set_title("Patches per month (by email date)")
    ax_vol.set_ylabel("Patches")
    ax_vol.legend(frameon=False)

    # (2) Monthly match rate.
    ax_rate.plot(months, monthly["match_rate"] * 100, color="#2b6cb0", label="Matches")
    ax_rate.plot(
        months,
        monthly["confident_match_rate"] * 100,
        color="#dd6b20",
        label="Confident matches",
    )
    ax_rate.set_title("Match rate per month")
    ax_rate.set_ylabel("% of evaluated patches")
    ax_rate.set_ylim(0, 100)
    ax_rate.legend(frameon=False)

    # (3) Distribution of integration latency (clipped at the 99th percentile).
    if latency.len() > 0:
        upper = latency.quantile(0.99)
        shown = latency.filter(latency <= upper)
        median = latency.median()
        ax_hist.hist(shown.to_numpy(), bins=60, color="#2b6cb0")
        ax_hist.axvline(median, color="#dd6b20", linestyle="--", label=f"Median: {median:.1f} d")
        ax_hist.legend(frameon=False)
    ax_hist.set_title(f"Integration latency ({kind}; up to the 99th percentile)")
    ax_hist.set_xlabel("Days from email to commit")
    ax_hist.set_ylabel("Patches")

    # (4) Median latency per month with the interquartile range.
    lat = monthly.filter(pl.col("latency_median").is_not_null())
    lat_months = lat["month"].to_list()
    ax_lat.fill_between(
        lat_months,
        lat["latency_p25"],
        lat["latency_p75"],
        color="#c7d3e3",
        label="Interquartile range",
    )
    ax_lat.plot(lat_months, lat["latency_median"], color="#2b6cb0", label="Median")
    ax_lat.set_title("Integration latency per month")
    ax_lat.set_ylabel("Days from email to commit")
    ax_lat.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.95)

    for ax in (ax_vol, ax_rate, ax_lat):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)

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
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Temporal analysis of matching results: volume, match rate and latency."
    )
    parser.add_argument("--config", required=True, help="Path to config.toml.")
    parser.add_argument("--list", dest="list_name", default="all", help="List name, or 'all'.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="PNG path for the figure.")
    parser.add_argument(
        "--csv",
        default=None,
        help="Monthly summary CSV path (default: next to the figure, with .csv).",
    )
    parser.add_argument(
        "--confident-only",
        action="store_true",
        help="Use only confident matches (score >= matching.autoaccept) for latency.",
    )
    parser.add_argument("--dpi", type=int, default=150)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)

    monthly = monthly_activity(config, args.list_name, args.confident_only).collect()
    if monthly.is_empty():
        raise SystemExit("No evaluated patches with an email date were found.")
    latency = (
        matched_latency(config, args.list_name, args.confident_only)
        .select("latency_days")
        .collect()
        .to_series()
    )

    output = Path(args.output)
    csv_path = Path(args.csv) if args.csv else output.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    monthly.write_csv(csv_path)

    plot_temporal(
        monthly,
        latency,
        output,
        title=f"Temporal analysis - list: {args.list_name}",
        confident_only=args.confident_only,
        dpi=args.dpi,
    )
    print(f"Saved figure to {output}")
    print(f"Saved {monthly.height} monthly row(s) to {csv_path}")


if __name__ == "__main__":
    main()