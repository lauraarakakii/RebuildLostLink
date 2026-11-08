import polars as pl
import pytest

from rebuild_lost_link import analysis
from rebuild_lost_link.analysis import latency, patch_size
from rebuild_lost_link.analysis import quality as cov


def test_coverage_counts_source_evaluated_and_matches(analysis_config):
    row = cov.coverage(analysis_config, "all").collect().to_dicts()[0]

    assert row["source_emails"] == 5
    assert row["evaluated_patches"] == 4
    assert row["matches"] == 2
    assert row["confident_matches"] == 1
    assert row["without_candidate"] == 1
    assert row["below_threshold"] == 1
    assert row["mean_score"] == pytest.approx((0.95 + 0.6 + 0.3) / 3)


def test_score_bands_classify_by_decision(analysis_config):
    bands = cov.score_bands(analysis_config, "all").collect().sort("result_band")

    assert bands["result_band"].to_list() == [
        "below_threshold",
        "confident_match",
        "no_candidate",
        "review_match",
    ]
    assert bands.filter(pl.col("result_band") == "confident_match")["mean_score"][0] == 0.95


def test_commit_reuse_lists_commits_with_several_emails(tmp_path, analysis_config):
    path = tmp_path / "enriched" / "list=netdev" / "data.parquet"
    pl.DataFrame(
        {
            "message_id": ["a", "b", "c"],
            "best_commit": ["h1", "h1", "h2"],
            "score": [0.9, 0.7, 0.8],
            "is_match": [True, True, True],
        }
    ).write_parquet(path)

    result = cov.commit_reuse(analysis_config, "all").collect()

    assert result.select("best_commit", "matched_emails").to_dicts() == [
        {"best_commit": "h1", "matched_emails": 2}
    ]


def test_match_errors_groups_by_message(tmp_path, analysis_config):
    path = tmp_path / "enriched" / "list=netdev" / "data.parquet"
    pl.DataFrame(
        {"message_id": ["a", "b"], "score": [None, None], "error": ["boom", "boom"]},
        schema_overrides={"score": pl.Float64},
    ).write_parquet(path)

    assert cov.match_errors(analysis_config, "all").collect().to_dicts() == [
        {"list": "netdev", "error": "boom", "occurrences": 2}
    ]


def test_patch_size_counts_changed_lines_from_source(analysis_config):
    result = patch_size.patch_size_outcomes(analysis_config, "all").collect().sort("size_band")

    assert result.select("size_band", "source_patches", "matches").to_dicts() == [
        {"size_band": "medium_21_100", "source_patches": 1, "matches": 1},
        {"size_band": "small_1_20", "source_patches": 4, "matches": 1},
    ]


def test_patch_size_by_sender_classifies_domains(analysis_config):
    result = patch_size.patch_size_outcomes_by_sender(analysis_config, "all").collect()

    counts = result.group_by("sender_type").agg(pl.col("source_patches").sum())
    assert dict(counts.iter_rows()) == {
        "vendor": 1,
        "infrastructure": 1,
        "third_party": 1,
        "community": 2,
    }


def test_integration_latency_uses_commit_minus_email_date(analysis_config):
    row = latency.integration_latency(analysis_config, "all").collect().to_dicts()[0]

    assert row["matched_patches"] == 2
    assert row["share_within_7d"] == 0.5  # 2.5 days and 10.0 days
    assert row["median_days"] == pytest.approx(6.25)


def test_run_writes_one_csv_per_analysis(tmp_path, analysis_config):
    out = tmp_path / "out"

    assert analysis.run(analysis_config, ["coverage", "score_bands"], "all", str(out)) == 0

    assert sorted(p.name for p in out.iterdir()) == ["coverage.csv", "score_bands.csv"]


def test_run_all_by_default_and_unknown_name_fails(tmp_path, analysis_config):
    out = tmp_path / "out"

    assert analysis.run(analysis_config, [], "all", str(out)) == 0
    assert {p.stem for p in out.iterdir()} == set(analysis.ANALYSES)
    assert analysis.run(analysis_config, ["nope"], "all", str(out)) == 1
