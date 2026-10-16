"""Candidate-search errors grouped for diagnosis."""

from __future__ import annotations

import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched


def build(config: Config, list_name: str) -> pl.LazyFrame:
    """Aggregate candidate-search errors for diagnosis."""
    return (
        scan_enriched(config, list_name)
        .filter(pl.col("error").is_not_null())
        .group_by("list", "error")
        .agg(pl.len().alias("occurrences"))
        .sort(["occurrences", "list", "error"], descending=[True, False, False])
    )


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "match_errors")
