"""Analyses over the matching results."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

import polars as pl

from ..config import Config
from .data import write_csv
from .latency import integration_latency
from .patch_size import patch_size_outcomes, patch_size_outcomes_by_sender
from .quality import commit_reuse, coverage, match_errors, score_bands

logger = logging.getLogger(__name__)

Analysis = Callable[[Config, str], pl.LazyFrame]

ANALYSES: dict[str, Analysis] = {
    f.__name__: f
    for f in (
        coverage,
        score_bands,
        match_errors,
        commit_reuse,
        patch_size_outcomes,
        patch_size_outcomes_by_sender,
        integration_latency,
    )
}


def run(
    config: Config,
    names: Iterable[str] = (),
    lists: str = "all",
    output_dir: str = "output/analysis",
) -> int:
    selected = list(names) or list(ANALYSES)
    unknown = [name for name in selected if name not in ANALYSES]
    if unknown:
        logger.error("Unknown analysis: %s. Available: %s", ", ".join(unknown), ", ".join(ANALYSES))
        return len(unknown)

    failures = 0
    for name in selected:
        try:
            write_csv(ANALYSES[name](config, lists), output_dir, name)
        except Exception:
            failures += 1
            logger.exception("Analysis '%s' failed", name)
    return failures
