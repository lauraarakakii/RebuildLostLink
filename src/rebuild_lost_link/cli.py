"""Command line: ``rebuild-lost-link [run|repo|match|enrich|analyze]``."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections.abc import Callable

from . import analysis, enrich, pipeline
from .config import DEFAULT_CONFIG_PATH, Config, load_config
from .repo_setup import ensure_repo

logger = logging.getLogger(__name__)


def _repo(config: Config) -> None:
    ensure_repo(config.repo, config.paths.repo_path)


def _clone(config: Config) -> None:
    forced = dataclasses.replace(config.repo, auto_clone=True)
    ensure_repo(forced, config.paths.repo_path)


# Stages of ``run``, in order; each depends on the previous one.
STEPS: dict[str, Callable[[Config], None]] = {
    "repo": _repo,
    "match": pipeline.run,
    "enrich": enrich.run,
}


COMMANDS = {
    "run": STEPS,
    "repo": {"repo": _clone},
    "match": {"match": pipeline.run},
    "enrich": {"enrich": enrich.run},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rebuild-lost-link",
        description="Link Linux kernel patch emails (LKML5Ws) to the commits that integrate them.",
    )
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH, help="TOML configuration.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="repo -> match -> enrich (default).")
    sub.add_parser("repo", help="Clone the kernel repository at paths.repo_path if missing.")
    sub.add_parser("match", help="Match patch emails to commits (one CSV per list).")
    sub.add_parser("enrich", help="Write the match CSVs as Parquet partitioned by list.")
    analyze = sub.add_parser("analyze", help="Write analysis CSVs from the matching results.")
    analyze.add_argument(
        "names", nargs="*", help=f"Analyses (default: all): {', '.join(analysis.ANALYSES)}"
    )
    analyze.add_argument(
        "-l", "--list", dest="lists", default="all", help="Name(s), comma-separated, or 'all'."
    )
    analyze.add_argument("-o", "--output-dir", default="output/analysis")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    command = args.command or "run"

    if command == "analyze":
        return 1 if analysis.run(config, args.names, args.lists, args.output_dir) else 0

    for name, step in COMMANDS[command].items():
        logger.info("Starting %s...", name)
        try:
            step(config)
        except Exception:
            logger.exception("Step '%s' failed", name)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
