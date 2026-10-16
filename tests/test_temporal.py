from datetime import datetime

import pytest

from lkml_ground_truth.analysis import temporal


def test_matched_latency_in_days(analysis_config):
    result = temporal.matched_latency(analysis_config, "all").collect().sort("message_id")

    assert result["message_id"].to_list() == ["a", "b"]
    assert result["latency_days"].to_list() == pytest.approx([2.5, 10.0])


def test_matched_latency_confident_only(analysis_config):
    result = temporal.matched_latency(analysis_config, "all", confident_only=True).collect()

    assert result["message_id"].to_list() == ["a"]


def test_monthly_activity_counts_and_rates(analysis_config):
    result = temporal.build(analysis_config, "all").collect()

    assert result["month"].to_list() == [datetime(2024, 1, 1), datetime(2024, 2, 1)]
    assert result["evaluated_patches"].to_list() == [2, 2]
    assert result["matches"].to_list() == [2, 0]
    assert result["confident_matches"].to_list() == [1, 0]
    assert result["match_rate"].to_list() == [1.0, 0.0]
    assert result["latency_median"].to_list()[1] is None


def test_main_writes_figure_and_csv(analysis_config, tmp_path):
    out = tmp_path / "out"

    temporal.main(analysis_config, str(out), "all")

    assert (out / "temporal.svg").stat().st_size > 0
    assert (out / "temporal.csv").exists()


def test_main_without_data_writes_nothing(analysis_config, tmp_path, monkeypatch):
    import polars as pl

    monkeypatch.setattr(temporal, "build", lambda *args: pl.DataFrame({"month": []}).lazy())

    temporal.main(analysis_config, str(tmp_path / "out"), "all")

    assert not (tmp_path / "out").exists()
