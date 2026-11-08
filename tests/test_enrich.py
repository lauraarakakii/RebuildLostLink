from datetime import datetime

import polars as pl
import pytest

from rebuild_lost_link.config import load_config
from rebuild_lost_link.enrich import enrich_list, run


@pytest.fixture
def config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""
[paths]
repo_path = "repo"
dataset_root = "{tmp_path / 'dataset'}"
enriched_root = "{tmp_path / 'enriched'}"
list_name = "all"
output_path = "{tmp_path}/matches_{{list}}.csv"
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
    return load_config(cfg)


def _write_matches(config, name):
    pl.DataFrame(
        {
            "message_id": ["a@x", "b@x"],
            "best_commit": ["deadbeef", None],
            "commit_date": ["2024-01-12T09:00:00-03:00", None],
            "score": [0.91, 0.42],
            "is_match": [True, True],
        },
        schema_overrides={"commit_date": pl.Utf8},
    ).write_csv(config.paths.resolved_output_path(name))


def test_enrich_writes_parquet_with_utc_naive_commit_date(config):
    _write_matches(config, "netdev")

    enrich_list(config, "netdev")

    out = pl.read_parquet(config.paths.enriched_parquet_path("netdev"))
    assert out.height == 2
    assert out["commit_date"][0] == datetime(2024, 1, 12, 12, 0)
    assert out["commit_date"][1] is None


def test_enrich_missing_csv_explains_what_to_run(config):
    with pytest.raises(FileNotFoundError, match="matching step"):
        enrich_list(config, "netdev")


def test_run_enriches_every_list_with_a_match_csv(config):
    for name in ("netdev", "bpf"):
        _write_matches(config, name)

    run(config)

    for name in ("netdev", "bpf"):
        assert pl.read_parquet(config.paths.enriched_parquet_path(name)).height == 2


def test_enrich_drops_commits_of_rows_that_are_not_matches(config):
    pl.DataFrame(
        {
            "message_id": ["a@x", "b@x"],
            "best_commit": ["deadbeef", "cafebabe"],
            "commit_date": ["2024-01-12T09:00:00-03:00", "2024-02-01T09:00:00-03:00"],
            "score": [0.91, 0.0],
            "is_match": [True, False],
        }
    ).write_csv(config.paths.resolved_output_path("netdev"))

    enrich_list(config, "netdev")

    out = pl.read_parquet(config.paths.enriched_parquet_path("netdev"))
    assert out["best_commit"].to_list() == ["deadbeef", None]
    assert out["commit_date"][1] is None
