#!/usr/bin/env python3
"""Share of patch emails that became a commit, per mailing list (from R3LKD)."""
import argparse
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  

DEFAULT_LISTS = [
    "linux-iio",
    "linux-arm-kernel",
    "linux-mm",
    "linux-toolchains",
    "amd-gfx",
    "alsa-devel",
]


def make_row(name, patches, matched, confident=None, errors=None) -> dict:
    return {
        "list": name,
        "patches": patches,
        "matched": matched,
        "confident": confident,
        "non_confident": None if confident is None else matched - confident,
        "errors": errors,
        "match_pct": 100.0 * matched / patches,
        "confident_pct": None if confident is None else 100.0 * confident / patches,
    }


def parse_values(items: list[str]) -> list[dict]:
    rows = []
    for item in items:
        parts = item.split(":")
        if len(parts) not in (3, 4):
            sys.exit(f"Bad --values item '{item}': use name:patches:matched[:confident]")
        nums = [int(p.replace(",", "").replace("_", "")) for p in parts[1:]]
        patches, matched = nums[0], nums[1]
        confident = nums[2] if len(nums) == 3 else None
        if patches <= 0 or matched > patches or (confident is not None and confident > matched):
            sys.exit(f"Inconsistent numbers in '{item}' (need matched <= patches, confident <= matched)")
        rows.append(make_row(parts[0], patches, matched, confident))
    return rows


def source_for(name: str, enriched: str, output: str):
    parquet = os.path.join(enriched, f"list={name}", "data.parquet")
    if os.path.isfile(parquet):
        return f"read_parquet('{parquet}')", parquet
    csv_path = os.path.join(output, f"matches_{name}.csv")
    if os.path.isfile(csv_path):
        return f"read_csv('{csv_path}', header = true)", csv_path
    return None, None


def aggregate(lists: list[str], enriched: str, output: str) -> list[dict]:
    import duckdb  

    con = duckdb.connect()
    rows = []
    for name in lists:
        source, path = source_for(name, enriched, output)
        if source is None:
            print(f"[skip] {name}: no enriched Parquet or matches CSV found "
                  f"(looked in {enriched}/ and {output}/)", file=sys.stderr)
            continue
        patches, matched, confident, errors = con.execute(
            f"""
            WITH t AS (
                SELECT
                    (error IS NULL OR CAST(error AS VARCHAR) = '')            AS ok,
                    COALESCE(TRY_CAST(is_match AS BOOLEAN), FALSE)            AS m,
                    COALESCE(TRY_CAST(is_confident_match AS BOOLEAN), FALSE)  AS c
                FROM {source}
            )
            SELECT
                COUNT(*) FILTER (WHERE ok),
                COUNT(*) FILTER (WHERE ok AND m),
                COUNT(*) FILTER (WHERE ok AND c),
                COUNT(*) FILTER (WHERE NOT ok)
            FROM t
            """
        ).fetchone()
        if patches == 0:
            print(f"[skip] {name}: no evaluated patches in {path}", file=sys.stderr)
            continue
        print(f"[ok]   {name}: read {path}", file=sys.stderr)
        rows.append(make_row(name, patches, matched, confident, errors))
    return rows


def plot(rows: list[dict], out_prefix: str) -> None:
    rows = sorted(rows, key=lambda r: r["match_pct"]) 
    names = [r["list"] for r in rows]
    has_conf = all(r["confident"] is not None for r in rows)

    plt.rcParams.update({"font.size": 9, "font.family": "sans-serif"})
    fig, ax = plt.subplots(figsize=(7.0, max(2.0, 0.42 * len(rows) + 1.0)))
    y = list(range(len(rows)))
    if has_conf:
        conf = [r["confident_pct"] for r in rows]
        nonconf = [r["match_pct"] - r["confident_pct"] for r in rows]
        ax.barh(y, conf, color="#1f4e8c", label="Confident match")
        ax.barh(y, nonconf, left=conf, color="#9db9de", label="Match requiring review")
        ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2,
                  frameon=False, fontsize=8, borderaxespad=0.4)
    else:
        ax.barh(y, [r["match_pct"] for r in rows], color="#1f4e8c")

    for i, r in enumerate(rows):
        ax.text(
            r["match_pct"] + 1.0,
            i,
            f"{r['matched']:,} / {r['patches']:,} ({r['match_pct']:.1f}%)",
            va="center",
            fontsize=8,
        )

    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Patch emails with a reported commit (%)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{out_prefix}.pdf")
    fig.savefig(f"{out_prefix}.png", dpi=300)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--values", nargs="*", metavar="NAME:PATCHES:MATCHED[:CONFIDENT]",
                    help="typed values, one item per list (skips the project files)")
    ap.add_argument("--lists", nargs="*", default=DEFAULT_LISTS, help="mailing lists to include")
    ap.add_argument("--enriched", default="output/enriched", help="enriched output directory")
    ap.add_argument("--output", default="output", help="directory with matches_<list>.csv")
    ap.add_argument("--fig", default="figures/match_rate_by_list", help="figure path prefix (no extension)")
    ap.add_argument("--csv", default="output/analysis/match_rate_by_list.csv", help="summary CSV path")
    args = ap.parse_args()

    rows = parse_values(args.values) if args.values else aggregate(args.lists, args.enriched, args.output)
    if not rows:
        print("No data found for any list. Run `match` (and `enrich`) first, and check the list names "
              "against the folders in your output directory.", file=sys.stderr)
        return 1

    for path in (args.fig, args.csv):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    rows_by_size = sorted(rows, key=lambda r: r["patches"], reverse=True)
    with open(args.csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_by_size[0].keys()))
        w.writeheader()
        for r in rows_by_size:
            w.writerow({k: ("" if v is None else round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})

    plot(rows, args.fig)
    print()
    for r in rows_by_size:
        print(f"{r['list']:<20} {r['matched']:>9,} / {r['patches']:<9,} {r['match_pct']:5.1f}%")
    print(f"\nWrote {args.fig}.pdf, {args.fig}.png and {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
