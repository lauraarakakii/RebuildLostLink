"""Pipeline orchestration from one or more datasets to match CSV files."""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Pool
from pathlib import Path

import polars as pl

from .config import Config
from .dataset_io import read_parquet_safe
from .engine import init_worker_globals, process_row

logger = logging.getLogger(__name__)
_RESULT_SCHEMA = {
    "message_id": pl.Utf8,
    "best_commit": pl.Utf8,
    "commit_date": pl.Utf8,
    "file_size": pl.Int64,
    "line_size": pl.Int64,
    "hunk_size": pl.Int64,
    "score": pl.Float64,
    "is_match": pl.Boolean,
    "is_confident_match": pl.Boolean,
    "error": pl.Utf8,
}


def _checkpoint_path(output_path: str) -> Path:
    return Path(output_path).with_suffix(".ckpt")


def _load_checkpoint(output_path: str) -> tuple[list[dict], set[str]]:
    ckpt = _checkpoint_path(output_path)
    if not ckpt.exists():
        return [], set()
    try:
        logger.info("Checkpoint found: %s; loading...", ckpt)
        df = pl.read_csv(ckpt, schema_overrides=_RESULT_SCHEMA)
        rows = df.to_dicts()
        ids = {r["message_id"] for r in rows if r.get("message_id")}
        logger.info(
            "Checkpoint found: %d rows already processed (%s); resuming.",
            len(rows),
            ckpt,
        )
        return rows, ids
    except Exception as exc:
        logger.warning("Could not load checkpoint (%s): %s. Starting from scratch.", ckpt, exc)
        return [], set()


def _append_checkpoint(ckpt: Path, new_rows: list[dict]) -> None:
    if not new_rows:
        return
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    write_header = not ckpt.exists() or ckpt.stat().st_size == 0
    df = pl.DataFrame(new_rows, schema=_RESULT_SCHEMA, infer_schema_length=None)
    with open(ckpt, "ab") as f:
        df.write_csv(f, include_header=write_header)


def process_list(config: Config, list_name: str) -> None:
    output_path = config.paths.resolved_output_path(list_name)
    ckpt = _checkpoint_path(output_path)

    logger.info("=== List: %s ===", list_name)
    df = read_parquet_safe(config.paths.parquet_glob(list_name))
    patches = df.filter(pl.col("code").is_not_null())
    logger.info("%d emails with a diff (of %d)", patches.height, df.height)

    results, done_ids = _load_checkpoint(output_path)
    if done_ids:
        patches = patches.filter(~pl.col("message_id").is_in(done_ids))
        logger.info("%d emails remaining after checkpoint", patches.height)

    perf = config.performance
    batch: list[dict] = []
    if patches.height:
        workers = perf.resolved_num_workers()
        logger.info("Processing with %d worker process(es)...", workers)
        with Pool(workers) as pool:
            rows = patches.iter_rows(named=True)
            for i, result in enumerate(
                pool.imap_unordered(process_row, rows, chunksize=perf.chunksize), start=1
            ):
                if result is not None:
                    results.append(result)
                    batch.append(result)
                if perf.checkpoint_every > 0 and len(batch) >= perf.checkpoint_every:
                    _append_checkpoint(ckpt, batch)
                    batch.clear()
                if i % perf.progress_every == 0 or i == patches.height:
                    logger.info("processed %d/%d...", i, patches.height)
        if perf.checkpoint_every > 0:
            _append_checkpoint(ckpt, batch)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out = pl.DataFrame(results, schema=_RESULT_SCHEMA, infer_schema_length=None)
    out.write_csv(output_path)
    logger.info("%d results saved to %s", out.height, output_path)
    n_errors = out["error"].is_not_null().sum()
    if n_errors:
        logger.warning("%d rows had errors; see the 'error' column.", n_errors)
    ckpt.unlink(missing_ok=True)


def _process_lists(config: Config, names: list[str]) -> None:
    n_parallel = config.performance.resolved_parallel_lists(len(names))
    if n_parallel <= 1:
        for name in names:
            process_list(config, name)
        return
    per_list = max(1, config.performance.resolved_num_workers() // n_parallel)
    derived = dataclasses.replace(
        config, performance=dataclasses.replace(config.performance, num_workers=per_list)
    )
    logger.info("%d lists at a time x %d workers each", n_parallel, per_list)
    with ThreadPoolExecutor(max_workers=n_parallel) as executor:
        for future in as_completed([executor.submit(process_list, derived, n) for n in names]):
            future.result()


def run(config: Config) -> None:
    logger.info("Opening repository and building/loading index: %s", config.paths.repo_path)
    init_worker_globals(config)

    list_name = config.paths.list_name
    if list_name.lower() in ("all", "*"):
        names = config.paths.available_lists()
        logger.info(
            "list_name = '%s' -> %d lists from %s", list_name, len(names), config.paths.dataset_root
        )
    else:
        names = [list_name]
    _process_lists(config, names)
