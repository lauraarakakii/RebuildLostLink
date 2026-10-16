"""Helpers shared by the analyses: result writing and common expressions."""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


def count_true(column: str) -> pl.Expr:
    """Count rows where a nullable boolean column is true."""
    return pl.when(pl.col(column).fill_null(False)).then(1).otherwise(0).sum()


def ensure_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(result: pl.LazyFrame | pl.DataFrame, output_dir: str | Path, name: str) -> Path:
    """Collect ``result`` if needed and save it as ``<output_dir>/<name>.csv``."""
    frame = result.collect() if isinstance(result, pl.LazyFrame) else result
    path = ensure_output_dir(output_dir) / f"{name}.csv"
    frame.write_csv(path)
    logger.info("Saved %d row(s) to %s", frame.height, path)
    return path
