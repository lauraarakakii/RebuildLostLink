#!/usr/bin/env python3
"""Export commits from a Linux clone as JSON Lines (``commit_id`` and ``diff`` per line)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git failed")
    return result.stdout


def commit_ids(args: argparse.Namespace) -> list[str]:
    command = ["log", "--format=%H", "--no-renames"]
    if args.since:
        command.append(f"--since={args.since}")
    if args.until:
        command.append(f"--until={args.until}")
    command.append(args.ref)
    ids_in_period = git(args.repo, *command).splitlines()

    if not args.commit_list:
        return ids_in_period

    wanted = {
        line.strip().lower()
        for line in args.commit_list.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return [commit_id for commit_id in ids_in_period if commit_id.lower() in wanted]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Local Linux clone.")
    parser.add_argument("--output", type=Path, required=True, help="Output .jsonl file.")
    parser.add_argument("--ref", default="HEAD", help="Ref to walk (default: HEAD).")
    parser.add_argument("--since", help="Start date accepted by git, e.g. 2025-01-01.")
    parser.add_argument("--until", help="End date accepted by git, e.g. 2025-12-31.")
    parser.add_argument(
        "--commit-list",
        type=Path,
        help="File with one commit hash per line; restricts the export to these commits.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.repo.is_dir():
        raise SystemExit(f"Git clone not found: {args.repo}")
    if args.commit_list and not args.commit_list.is_file():
        raise SystemExit(f"Commit list not found: {args.commit_list}")

    try:
        ids = commit_ids(args)
    except RuntimeError as exc:
        raise SystemExit(f"Could not query the repository: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as output:
        for commit_id in ids:
            try:
                diff = git(
                    args.repo,
                    "show",
                    "--format=",
                    "--patch",
                    "--no-ext-diff",
                    "--no-renames",
                    commit_id,
                )
            except RuntimeError as exc:
                print(f"WARNING: skipping {commit_id}: {exc}", file=sys.stderr)
                continue
            output.write(json.dumps({"commit_id": commit_id, "diff": diff}, ensure_ascii=False))
            output.write("\n")
            written += 1

    print(f"Exported {written} commits to {args.output}")


if __name__ == "__main__":
    main()
