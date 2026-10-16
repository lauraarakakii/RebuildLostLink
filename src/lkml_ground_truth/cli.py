"""Command-line entry point (``lkml-ground-truth`` / ``python -m lkml_ground_truth``)."""

from __future__ import annotations

import argparse
import logging

from .analysis import main as analysis_main
from .analysis.query import run as run_query_command
from .config import DEFAULT_CONFIG_PATH, load_config
from .steps import main as steps_main

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lkml-ground-truth",
        description=(
            "Match patch emails from a MailingListsHeritage dataset with "
            "commits in the Linux Git repository using PaStA's comparison engine."
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the TOML configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run every step in order: repo -> matching -> enrich "
        "(the default when no subcommand is given).",
    )
    steps_main.add_arguments(run_parser)

    clone_parser = subparsers.add_parser(
        "clone-repo",
        help=(
            "Clone (or validate) the configured kernel repository at "
            "'paths.repo_path' without running the other steps."
        ),
    )
    clone_parser.add_argument(
        "--force",
        action="store_true",
        help="Clone even when auto_clone=false in config.toml.",
    )
    subparsers.add_parser( 
        "enrich",
        help="Join the match CSV back into the original dataset by message_id " \
        "and write enriched Parquet data to 'paths.enriched_root'. "
        "Already part of 'run'; use this to re-run it on its own."
    )

    analysis_parser = subparsers.add_parser(
        "analysis",
        help="Run analyses over the original and enriched datasets "
        "(all default analyses unless --analysis is given).",
    )
    analysis_main.add_arguments(analysis_parser)

    query_parser = subparsers.add_parser( 
        "query",
        help="Run Polars SQL queries against the 'original' and 'enriched' "
        "Parquet tables. Without SQL, open an interactive REPL.",
    )

    query_parser.add_argument(
    "sql",
    nargs="?",
    default=None,
    help="SQL query. Tables: 'original' (LKML5Ws dataset) and 'enriched' (matches). "
    "Example: \"SELECT * FROM enriched WHERE is_match=true LIMIT 10\". "
    "Omit to open interactive mode."
    )
    query_parser.add_argument(
        "-l",
        "--list",
        dest="list_name",
        default=None,
        help="List to query (default: 'paths.list_name'). Use 'all' for every list "
        "and add the 'list' column.",
    )
    query_parser.add_argument(
        "--output",
        default=None,
        help="Output file. Without it, results are printed to the terminal."
    )
    query_parser.add_argument(
        "-f",
        "--format",
        dest="fmt",
        choices=("csv", "parquet", "json", "ndjson"),
        default=None,
        help="Export format (default: inferred from --output extension).",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum terminal rows (0 = all). Does not affect exports. Default: 20.",
    )
    return parser


def _run_step(config, step: str, **options) -> int:
    registry = steps_main.build_registry(steps_main.RunOptions(config=config, **options))
    return steps_main.run_steps(registry, step)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = load_config(args.config)

    command = args.command or "run"

    if command == "run":
        return steps_main.run(config, args)

    if command == "clone-repo":
        return _run_step(config, "repo", force_clone=args.force)

    if command == "enrich":
        return _run_step(config, "enrich")

    if command == "analysis":
        return analysis_main.run(config, args)

    if command == "query":
        # Without SQL, ``run`` opens a REPL and preserves its SQLContext for
        # subsequent queries. With SQL, it executes only the supplied query.
        run_query_command(
            config,
            args.sql,
            list_name=args.list_name,
            output=args.output,
            fmt=args.fmt,
            limit=args.limit,
        )
        return 0

    raise AssertionError(f"Unhandled command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
