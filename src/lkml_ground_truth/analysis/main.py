"""Orchestrator for the analyses (``python -m lkml_ground_truth.analysis``).

Mirrors the MLH analysis orchestrator: every analysis lives in its own module
and exposes ``main(config, output_dir, list_name)``. Without a selection all
default analyses run; a failure in one is logged and does not stop the others.
Non-default analyses (the interactive ``sql_querier``) only run when selected.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_CONFIG_PATH, Config, load_config
from . import (
    commit_reuse,
    dataset_coverage,
    latency_distribution,
    latency_per_month,
    match_coverage,
    match_errors,
    match_rate_per_month,
    matched_pairs,
    patches_per_month,
    score_bands,
    sql_querier,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "output/analysis"

# Every analysis, in execution order. Keep in sync with build_registry().
ANALYSIS_NAMES = (
    "dataset_coverage",
    "match_coverage",
    "score_bands",
    "match_errors",
    "commit_reuse",
    "matched_pairs",
    "patches_per_month",
    "match_rate_per_month",
    "latency_distribution",
    "latency_per_month",
    "sql_querier",
)

# Analyses that never run unless selected by name (interactive or needing input).
NON_DEFAULT_ANALYSES = ("sql_querier",)


@dataclass(frozen=True)
class RunOptions:
    """Everything an analysis may need; each analysis takes what it uses."""

    config: Config
    output_dir: str = DEFAULT_OUTPUT_DIR
    list_name: str = "all"
    confident_only: bool = False
    sql: str | None = None
    sql_output: str | None = None
    sql_format: str | None = None
    limit: int = 20


def build_registry(options: RunOptions) -> dict[str, Callable[[], None]]:
    """Map analysis names to zero-argument callables, in execution order."""
    config, out, lists = options.config, options.output_dir, options.list_name
    return {
        "dataset_coverage": lambda: dataset_coverage.main(config, out, lists),
        "match_coverage": lambda: match_coverage.main(config, out, lists),
        "score_bands": lambda: score_bands.main(config, out, lists),
        "match_errors": lambda: match_errors.main(config, out, lists),
        "commit_reuse": lambda: commit_reuse.main(config, out, lists),
        "matched_pairs": lambda: matched_pairs.main(config, out, lists),
        # one chart per analysis
        "patches_per_month": lambda: patches_per_month.main(
            config, out, lists, confident_only=options.confident_only
        ),
        "match_rate_per_month": lambda: match_rate_per_month.main(config, out, lists),
        "latency_distribution": lambda: latency_distribution.main(
            config, out, lists, confident_only=options.confident_only
        ),
        "latency_per_month": lambda: latency_per_month.main(
            config, out, lists, confident_only=options.confident_only
        ),
        # these below will not run by default
        "sql_querier": lambda: sql_querier.main(
            config,
            out,
            lists,
            sql=options.sql,
            output=options.sql_output,
            fmt=options.sql_format,
            limit=options.limit,
        ),
    }


def normalize_name(name: str | None) -> str:
    """Accept ``sql_querier`` and ``sql_querier.py`` alike."""
    name = (name or "").strip()
    return name.removesuffix(".py")


def run_analyses(registry: dict[str, Callable[[], None]], selection: str | None = None) -> int:
    """Run the selected analysis, or every default one. Return the failure count.

    An empty selection (or ``all``) runs the default analyses. A named analysis
    runs alone, and its errors propagate. An unknown name logs the available
    ones and counts as a failure.
    """
    name = normalize_name(selection)

    if name and name.lower() != "all":
        if name not in registry:
            logger.warning("Unknown analysis: %s", name)
            logger.warning("Available: %s", ", ".join(registry))
            return 1
        logger.info("Starting %s...", name)
        registry[name]()
        return 0

    failures = 0
    for analysis_name, analysis in registry.items():
        if analysis_name in NON_DEFAULT_ANALYSES:
            continue
        logger.info("Starting %s...", analysis_name)
        try:
            analysis()
        except Exception:
            failures += 1
            logger.exception("Failed to run %s analysis", analysis_name)
    return failures


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Analysis options, shared by this module's CLI and ``lkml-ground-truth analysis``."""
    parser.add_argument(
        "-a",
        "--analysis",
        default="",
        help="Analysis to run (default: all default analyses). "
        f"One of: {', '.join(ANALYSIS_NAMES)}. 'sql_querier' only runs when selected.",
    )
    parser.add_argument(
        "-l",
        "--list",
        dest="list_name",
        default="all",
        help="Mailing list(s): a name, a comma-separated list, or 'all' (default).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the results (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--confident-only",
        action="store_true",
        help="patches_per_month, latency_distribution, latency_per_month: use only "
        "confident matches (score >= matching.autoaccept).",
    )
    parser.add_argument(
        "--sql", help="sql_querier: SQL to run once and exit (omit for the interactive REPL)."
    )
    parser.add_argument(
        "--sql-output", help="sql_querier: save the result (CSV, Parquet, JSON or NDJSON)."
    )
    parser.add_argument(
        "--sql-format",
        choices=("csv", "parquet", "json", "ndjson"),
        help="sql_querier: output format; inferred from --sql-output when omitted.",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="sql_querier: terminal row limit (0 = all)."
    )


def run(config: Config, args: argparse.Namespace) -> int:
    """Run the analyses requested by parsed ``args``; return a process exit code."""
    options = RunOptions(
        config=config,
        output_dir=args.output_dir,
        list_name=args.list_name,
        confident_only=args.confident_only,
        sql=args.sql,
        sql_output=args.sql_output,
        sql_format=args.sql_format,
        limit=args.limit,
    )
    return 1 if run_analyses(build_registry(options), args.analysis) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lkml_ground_truth.analysis",
        description="Run analyses over the original and enriched LKML Ground Truth datasets.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the TOML configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args(argv)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    return run(load_config(args.config), args)


if __name__ == "__main__":
    raise SystemExit(main())
