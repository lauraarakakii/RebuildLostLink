"""Shared fixtures for the analysis tests."""

from datetime import datetime

import polars as pl
import pytest

from lkml_ground_truth.config import load_config


@pytest.fixture
def analysis_config(tmp_path):
    original_root = tmp_path / "dataset"
    enriched_root = tmp_path / "enriched"
    for root in (original_root, enriched_root):
        (root / "list=netdev").mkdir(parents=True)

    pl.DataFrame(
        {
            "message_id": ["a", "b", "c", "d", "e"],
            "date": [
                datetime(2024, 1, 10),
                datetime(2024, 1, 20),
                datetime(2024, 2, 5),
                datetime(2024, 2, 6),
                datetime(2024, 2, 6),
            ],
            "code": [
                ["diff --git a/a b/a\n+added\n-removed"],
                ["diff --git a/b b/b\n" + "+added\n" * 30 + "-removed"],
                ["diff --git a/c b/c\n+added\n-removed"],
                ["diff --git a/d b/d\n+added\n-removed"],
                ["diff --git a/e b/e\n+added\n-removed"],
            ],
            "in_reply_to": [None, "a", None, "c", None],
            "references": [[], ["a"], [], ["c"], []],
        }
    ).write_parquet(original_root / "list=netdev" / "part.parquet")

    # Mirrors the real schema: score as text, commit_date ISO 8601 with offset.
    pl.DataFrame(
        {
            "message_id": ["a", "b", "c", "d"],
            "best_commit": ["h1", "h2", "h3", None],
            "commit_date": [
                "2024-01-12T09:00:00-03:00",  # 12:00 UTC -> 2.5 days after email a
                "2024-01-30T00:00:00+00:00",  # 10.0 days
                "2024-02-06T00:00:00+00:00",  # 1.0 day
                None,
            ],
            "score": ["0.95", "0.6", "0.3", None],
            "is_match": [True, True, False, False],
            "is_confident_match": [True, False, False, False],
            "error": [None, None, None, None],
        }
    ).write_parquet(enriched_root / "list=netdev" / "data.parquet")

    path = tmp_path / "config.toml"
    path.write_text(
        f"""
[paths]
repo_path = "repo"
dataset_root = "{original_root}"
enriched_root = "{enriched_root}"
list_name = "netdev"
output_path = "output/matches_{{list}}.csv"
commit_index_cache = "cache.pickle"

[performance]
num_workers = 1
rebuild_index = false
chunksize = 1
progress_every = 1

[matching]
days_before = 3
days_after = 365
autoaccept = 0.8
interactive = 0.5
diff_lines_ratio = 0.4
heading = 0.7
filename = 0.7
message_diff_weight = 0.5
"""
    )
    return load_config(path)
