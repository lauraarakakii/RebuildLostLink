"""Orchestrator for the main execution (``rebuild-lost-link run``).

Mirrors the analysis orchestrator: every stage lives in its own module and
exposes ``main(config, ...)``. Without a selection all stages run in order
(repo -> matching -> enrich). Unlike the analyses, the stages depend on each
other (matching needs the repository, enrich needs the match CSVs), so a
failure stops the run instead of continuing with the next stage.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass

from ..config import Config
from . import enrich, matching, repo

logger = logging.getLogger(__name__)

# Every step, in execution order. Keep in sync with build_registry().
STEP_NAMES = ("repo", "matching", "enrich")


@dataclass(frozen=True)
class RunOptions:
    config: Config
    force_clone: bool = False


def build_registry(options: RunOptions) -> dict[str, Callable[[], None]]:
    """Map step names to zero-argument callables, in execution order."""
    config = options.config
    return {
        "repo": lambda: repo.main(config, force=options.force_clone),
        "matching": lambda: matching.main(config),
        "enrich": lambda: enrich.main(config),
    }


def normalize_name(name: str | None) -> str:
    """Accept ``matching`` and ``matching.py`` alike."""
    return (name or "").strip().removesuffix(".py")


def run_steps(registry: dict[str, Callable[[], None]], selection: str | None = None) -> int:
    """Run the selected step, or every step in order. Return a process exit code.

    An empty selection (or ``all``) runs every step and stops at the first
    failure. A named step runs alone and its errors propagate. An unknown name
    logs the available steps and returns 1.
    """
    name = normalize_name(selection)

    if name and name.lower() != "all":
        if name not in registry:
            logger.warning("Unknown step: %s", name)
            logger.warning("Available: %s", ", ".join(registry))
            return 1
        logger.info("Starting %s...", name)
        registry[name]()
        return 0

    for step_name, step in registry.items():
        logger.info("Starting %s...", step_name)
        try:
            step()
        except Exception:
            logger.exception(
                "Step '%s' failed; stopping because later steps depend on it", step_name
            )
            return 1
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Options of the ``run`` subcommand."""
    parser.add_argument(
        "-s",
        "--step",
        default="",
        help=f"Step to run (default: all, in order). One of: {', '.join(STEP_NAMES)}.",
    )
    parser.add_argument(
        "--force-clone",
        action="store_true",
        help="repo: clone even when repo.auto_clone is false.",
    )


def run(config: Config, args: argparse.Namespace) -> int:
    """Run the steps requested by parsed ``args``; return a process exit code."""
    options = RunOptions(config=config, force_clone=getattr(args, "force_clone", False))
    return run_steps(build_registry(options), getattr(args, "step", ""))
