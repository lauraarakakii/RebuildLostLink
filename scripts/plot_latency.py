#!/usr/bin/env python3
"""Time from patch email to commit, per mailing list (R3LKD joined with LKML5Ws)."""
import argparse
import csv
import glob
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator  

DEFAULT_LISTS = [
    "linux-iio",
    "linux-arm-kernel",
    "linux-mm",
    "linux-toolchains",
    "amd-gfx",
    "alsa-devel",
]

PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
LINESTYLES = ["-", "--", "-.", ":", "-", "--"]


def dataset_root_from_config(path: str = "config.toml"):
    try:
        import tomllib
    except ModuleNotFoundError:
        return None
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)
    return cfg.get("paths", {}).get("dataset_root")


def r3lkd_source(name: str, enriched: str, output: str):
    parquet = os.path.join(enriched, f"list={name}", "data.parquet")
    if os.path.isfile(parquet):
        return f"read_parquet('{parquet}')", parquet
    csv_path = os.path.join(output, f"matches_{name}.csv")
    if os.path.isfile(csv_path):
        return f"read_csv('{csv_path}', header = true)", csv_path
    return None, None


def latencies(con, name, args, dataset_root):
    """Return (reported matches, latency in days for matches found in LKML5Ws) or None."""
    src, src_path = r3lkd_source(name, args.enriched, args.output)
    if src is None:
        print(f"[skip] {name}: no R3LKD file found (looked in {args.enriched}/ and {args.output}/)",
              file=sys.stderr)
        return None
    lk_glob = os.path.join(dataset_root, f"list={name}", "*.parquet")
    if not glob.glob(lk_glob):
        print(f"[skip] {name}: no LKML5Ws Parquet at {lk_glob}", file=sys.stderr)
        return None

    cols = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{lk_glob}')").fetchall()]
    for needed in (args.id_col, args.date_col):
        if needed not in cols:
            sys.exit(f"Column '{needed}' not found in LKML5Ws ({lk_glob}).\n"
                     f"Available columns: {', '.join(cols)}\n"
                     f"Use --id-col / --date-col to name the right ones.")

    r_sql = f"""
        SELECT CAST(message_id AS VARCHAR) AS mid,
               TRY_CAST(commit_date AS TIMESTAMPTZ) AS cdate
        FROM {src}
        WHERE (error IS NULL OR CAST(error AS VARCHAR) = '')
          AND COALESCE(TRY_CAST(is_match AS BOOLEAN), FALSE)
    """
    matches = con.execute(f"SELECT COUNT(*) FROM ({r_sql})").fetchone()[0]
    lat = con.execute(
        f"""
        WITH r AS ({r_sql}),
        e AS (
            SELECT CAST("{args.id_col}" AS VARCHAR) AS mid,
                   MIN(TRY_CAST("{args.date_col}" AS TIMESTAMPTZ)) AS edate
            FROM read_parquet('{lk_glob}')
            GROUP BY 1
        )
        SELECT (epoch(r.cdate) - epoch(e.edate)) / 86400.0 AS d
        FROM r JOIN e USING (mid)
        WHERE r.cdate IS NOT NULL AND e.edate IS NOT NULL
        """
    ).fetchnumpy()["d"]
    print(f"[ok]   {name}: {src_path}", file=sys.stderr)
    return matches, np.asarray(lat, dtype=float)


def summarize(name, matches, lat) -> dict:
    pos = np.sort(lat[lat >= 0])
    row = {
        "list": name,
        "matches": matches,
        "joined": int(lat.size),
        "before_email": int((lat < 0).sum()),
        "n_used": int(pos.size),
    }
    if pos.size:
        q1, med, q3 = np.percentile(pos, [25, 50, 75])
        row.update({
            "q1_days": round(q1, 2), "median_days": round(med, 2), "q3_days": round(q3, 2),
            "within_7d_pct": round(100 * (pos <= 7).mean(), 1),
            "within_30d_pct": round(100 * (pos <= 30).mean(), 1),
            "within_90d_pct": round(100 * (pos <= 90).mean(), 1),
        })
    return row, pos


def plot(results: list, out_prefix: str) -> None:
    results = sorted(results, key=lambda t: t[0]["median_days"])  
    grid = np.logspace(np.log10(0.1), np.log10(400), 600)

    plt.rcParams.update({"font.size": 9, "font.family": "sans-serif"})
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for i, (row, pos) in enumerate(results):
        y = 100.0 * np.searchsorted(pos, grid, side="right") / pos.size
        ax.plot(grid, y, color=PALETTE[i % len(PALETTE)], linestyle=LINESTYLES[i % len(LINESTYLES)],
                linewidth=1.8, label=f"{row['list']} (n={row['n_used']:,})")

    for x in (7, 30, 90):
        ax.axvline(x, color="#bbbbbb", linewidth=0.8, linestyle=":", zorder=0)
    ax.set_xscale("log")
    ax.set_xlim(0.1, 400)
    ax.set_ylim(0, 100)
    ax.set_xticks([1, 7, 30, 90, 365])
    ax.set_xticklabels(["1", "7", "30", "90", "365"])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel("Days from patch email to commit (log scale)")
    ax.set_ylabel("Cumulative share of matched patches (%)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, frameon=False,
              fontsize=8, borderaxespad=0.4)
    fig.tight_layout()
    fig.savefig(f"{out_prefix}.pdf")
    fig.savefig(f"{out_prefix}.png", dpi=300)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lists", nargs="*", default=DEFAULT_LISTS, help="mailing lists to include")
    ap.add_argument("--dataset-root", default=None,
                    help="LKML5Ws root with list=<name>/*.parquet (default: paths.dataset_root in config.toml)")
    ap.add_argument("--enriched", default="output/enriched", help="enriched output directory")
    ap.add_argument("--output", default="output", help="directory with matches_<list>.csv")
    ap.add_argument("--id-col", default="message_id", help="message id column in LKML5Ws")
    ap.add_argument("--date-col", default="date", help="email date column in LKML5Ws")
    ap.add_argument("--fig", default="figures/latency_by_list", help="figure path prefix (no extension)")
    ap.add_argument("--csv", default="output/analysis/latency_by_list.csv", help="summary CSV path")
    args = ap.parse_args()

    dataset_root = args.dataset_root or dataset_root_from_config()
    if not dataset_root:
        sys.exit("LKML5Ws location unknown. Pass --dataset-root, or run from the project root "
                 "so that config.toml (paths.dataset_root) is found.")

    import duckdb  

    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
    except Exception:
        pass

    results = []
    for name in args.lists:
        got = latencies(con, name, args, dataset_root)
        if got is None:
            continue
        row, pos = summarize(name, *got)
        if pos.size == 0:
            print(f"[skip] {name}: no matched patch with latency >= 0 after the join", file=sys.stderr)
            continue
        results.append((row, pos))
    if not results:
        print("Nothing to plot. Check the list names, the dataset root and the date/id columns.",
              file=sys.stderr)
        return 1

    for path in (args.fig, args.csv):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = [r for r, _ in sorted(results, key=lambda t: t[0]["n_used"], reverse=True)]
    with open(args.csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    plot(results, args.fig)
    print(f"\n{'list':<20}{'matches':>10}{'joined':>10}{'before':>8}{'median(d)':>11}{'<=7d':>7}{'<=30d':>7}{'<=90d':>7}")
    for r in rows:
        print(f"{r['list']:<20}{r['matches']:>10,}{r['joined']:>10,}{r['before_email']:>8,}"
              f"{r['median_days']:>11.1f}{r['within_7d_pct']:>6.1f}%{r['within_30d_pct']:>6.1f}%{r['within_90d_pct']:>6.1f}%")
    print(f"\nWrote {args.fig}.pdf, {args.fig}.png and {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
