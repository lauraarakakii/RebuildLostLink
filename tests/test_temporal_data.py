from datetime import datetime

import pytest

from lkml_ground_truth.analysis import temporal_data


def test_matched_latency_in_days(analysis_config):
    result = temporal_data.matched_latency(analysis_config, "all").collect().sort("message_id")

    assert result["message_id"].to_list() == ["a", "b"]
    assert result["latency_days"].to_list() == pytest.approx([2.5, 10.0])


def test_matched_latency_confident_only(analysis_config):
    result = temporal_data.matched_latency(analysis_config, "all", confident_only=True).collect()

    assert result["message_id"].to_list() == ["a"]


def test_monthly_activity_counts_and_rates(analysis_config):
    result = temporal_data.build(analysis_config, "all").collect()

    assert result["month"].to_list() == [datetime(2024, 1, 1), datetime(2024, 2, 1)]
    assert result["evaluated_patches"].to_list() == [2, 2]
    assert result["matches"].to_list() == [2, 0]
    assert result["confident_matches"].to_list() == [1, 0]
    assert result["match_rate"].to_list() == [1.0, 0.0]
    assert result["latency_median"].to_list()[1] is None


def test_load_monthly_returns_none_without_data(analysis_config, monkeypatch):
    import polars as pl

    monkeypatch.setattr(temporal_data, "build", lambda *args: pl.DataFrame({"month": []}).lazy())

    assert temporal_data.load_monthly(analysis_config, "all") is None
