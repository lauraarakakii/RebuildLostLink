#!/usr/bin/env python3
"""Join A (Git), B (LKML5Ws) and C (correlation) into one integrated list."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

csv.field_size_limit(sys.maxsize)


def read_jsonl(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def correlation_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".parquet":
        import polars as pl

        return pl.read_parquet(path).to_dicts()
    return read_csv(path)


def index_unique(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        if not value:
            raise ValueError(f"{label}: required field is empty: {key}")
        if value in indexed:
            raise ValueError(f"{label}: duplicate key {key}={value!r}")
        indexed[value] = row
    return indexed


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def save(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("w", encoding="utf-8") as target:
            for row in rows:
                target.write(json.dumps(row, ensure_ascii=False))
                target.write("\n")
    elif suffix == ".parquet":
        import polars as pl

        pl.DataFrame(rows).write_parquet(path)
    elif suffix == ".csv":
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=["message_id", "commit_hash", "github_diff", "lkml_diff"],
            )
            writer.writeheader()
            writer.writerows(rows)
    else:
        raise ValueError("Output must end in .jsonl, .csv or .parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--git-list",
        type=Path,
        required=True,
        help="List A: JSONL written by extract_kernel_diffs.py.",
    )
    parser.add_argument(
        "--lkml-list", type=Path, required=True, help="List B: CSV with columns message_id,diff."
    )
    parser.add_argument("--correlation", type=Path, required=True, help="List C: CSV or Parquet.")
    parser.add_argument(
        "--output", type=Path, required=True, help="Integrated list (.jsonl recommended)."
    )
    parser.add_argument(
        "--include-non-matches",
        action="store_true",
        help="Also keep rows of C whose is_match is not true.",
    )
    args = parser.parse_args()

    git_by_commit = index_unique(read_jsonl(args.git_list), "commit_id", "List A")
    lkml_by_message = index_unique(read_csv(args.lkml_list), "message_id", "List B")

    integrated: list[dict[str, str]] = []
    skipped = 0
    for row in correlation_rows(args.correlation):
        if not args.include_non_matches and not is_true(row.get("is_match")):
            skipped += 1
            continue
        message_id = str(row.get("message_id", "")).strip()
        commit_hash = str(row.get("commit_hash") or row.get("best_commit") or "").strip()
        if not message_id or not commit_hash:
            skipped += 1
            continue
        lkml = lkml_by_message.get(message_id)
        git_row = git_by_commit.get(commit_hash)
        if lkml is None or git_row is None:
            skipped += 1
            continue
        integrated.append(
            {
                "message_id": message_id,
                "commit_hash": commit_hash,
                "github_diff": str(git_row["diff"]),
                "lkml_diff": str(lkml["diff"]),
            }
        )

    try:
        index_unique(integrated, "message_id", "Integrated list")
    except ValueError as exc:
        raise SystemExit(f"Correlation is not 1:1 by message_id: {exc}") from exc
    save(integrated, args.output)
    print(f"Integrated list: {len(integrated)} rows saved to {args.output}; " f"{skipped} skipped.")


if __name__ == "__main__":
    main()
