"""Lazy readers and small helpers shared by every analysis."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import polars as pl

from ..config import Config

logger = logging.getLogger(__name__)

# Study window, applied to the email date (not the commit date).
STUDY_START = datetime(2016, 5, 1)
STUDY_END = datetime(2026, 6, 1)  # exclusive

ALL_LISTS = {"all", "*"}


def _list_names(root: Path, selection: str) -> list[str]:
    names = [name.strip() for name in (selection or "").split(",") if name.strip()]
    if names and not ALL_LISTS & {name.lower() for name in names}:
        return names
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {root}. Check config.toml.")
    return sorted(p.name.removeprefix("list=") for p in root.glob("list=*") if p.is_dir())


def scan_partitions(root: str, selection: str) -> pl.LazyFrame:
    base = Path(root)
    scans = [
        pl.scan_parquet(
            str(base / f"list={name}" / "*.parquet"), hive_partitioning=False
        ).with_columns(pl.lit(name).alias("list"))
        for name in _list_names(base, selection)
        if any((base / f"list={name}").glob("*.parquet"))
    ]
    if not scans:
        raise FileNotFoundError(f"No Parquet files in {base} for list(s): {selection}.")
    return pl.concat(scans, how="diagonal_relaxed")


def scan_source(config: Config, selection: str) -> pl.LazyFrame:
    return scan_partitions(config.paths.dataset_root, selection)


def scan_matches(config: Config, selection: str) -> pl.LazyFrame:
    """The matching results; ``score`` is cast because some runs stored it as text."""
    return scan_partitions(config.paths.enriched_root, selection).with_columns(
        pl.col("score").cast(pl.Float64, strict=False)
    )


def count_true(column: str) -> pl.Expr:
    return pl.col(column).fill_null(False).sum()


def rate(numerator: str, denominator: str) -> pl.Expr:
    return (
        pl.when(pl.col(denominator) > 0)
        .then(pl.col(numerator) / pl.col(denominator))
        .otherwise(None)
    )


def write_csv(frame: pl.LazyFrame | pl.DataFrame, output_dir: str | Path, name: str) -> Path:
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    path = path / f"{name}.csv"
    frame.write_csv(path)
    logger.info("Saved %d row(s) to %s", frame.height, path)
    return path
