import polars as pl
import pytest

from lkml_ground_truth.analysis import (
    commit_reuse,
    dataset_coverage,
    discussion_context,
    match_coverage,
    patch_size_outcomes,
    score_bands,
)


def test_dataset_coverage_joins_original_and_enriched(monkeypatch):
    original = pl.DataFrame(
        {
            "list": ["netdev", "netdev", "iio"],
            "message_id": ["a", "b", "c"],
        }
    ).lazy()
    enriched = pl.DataFrame(
        {
            "list": ["netdev", "iio"],
            "message_id": ["a", "c"],
            "is_match": [True, False],
            "is_confident_match": [True, False],
            "error": [None, "candidate_search: bad date"],
        }
    ).lazy()
    monkeypatch.setattr(dataset_coverage, "scan_original", lambda *args: original)
    monkeypatch.setattr(dataset_coverage, "scan_enriched", lambda *args: enriched)

    result = dataset_coverage.build(object(), "all").collect().sort("list")

    assert result.to_dicts() == [
        {
            "list": "iio",
            "source_emails": 1,
            "evaluated_patches": 1,
            "matches": 0,
            "confident_matches": 0,
            "errors": 1,
        },
        {
            "list": "netdev",
            "source_emails": 2,
            "evaluated_patches": 1,
            "matches": 1,
            "confident_matches": 1,
            "errors": 0,
        },
    ]


def test_score_analyses_accept_score_stored_as_text(analysis_config):
    # The enriched dataset may persist ``score`` as text; it must still aggregate.
    coverage = match_coverage.build(analysis_config, "all").collect()
    bands = score_bands.build(analysis_config, "all").collect().sort("result_band")

    assert coverage["mean_score"].to_list() == [pytest.approx((0.95 + 0.6 + 0.3) / 3)]
    assert bands["result_band"].to_list() == [
        "below_threshold",
        "confident_match",
        "no_candidate",
        "review_match",
    ]
    assert bands["mean_score"].to_list()[1] == pytest.approx(0.95)


def test_commit_reuse_lists_commits_with_several_emails(monkeypatch):
    enriched = pl.DataFrame(
        {
            "list": ["netdev"] * 3,
            "message_id": ["a", "b", "c"],
            "best_commit": ["h1", "h1", "h2"],
            "commit_date": ["2024-01-02", "2024-01-02", "2024-01-03"],
            "score": [0.9, 0.7, 0.8],
            "is_match": [True, True, True],
        }
    ).lazy()
    monkeypatch.setattr(commit_reuse, "scan_enriched", lambda *args: enriched)

    result = commit_reuse.build(object(), "all").collect()

    assert result.select("best_commit", "matched_emails").to_dicts() == [
        {"best_commit": "h1", "matched_emails": 2}
    ]


def test_discussion_context_joins_original_thread_metadata(analysis_config):
    result = discussion_context.build(analysis_config, "all").collect().sort("discussion_context")

    assert result.select(
        "discussion_context", "source_patches", "evaluated_patches", "matches", "confident_matches"
    ).to_dicts() == [
        {
            "discussion_context": "initial_submission",
            "source_patches": 3,
            "evaluated_patches": 2,
            "matches": 1,
            "confident_matches": 1,
        },
        {
            "discussion_context": "reply_or_revision",
            "source_patches": 2,
            "evaluated_patches": 2,
            "matches": 1,
            "confident_matches": 0,
        },
    ]


def test_patch_size_outcomes_counts_changed_lines_from_original(analysis_config):
    result = patch_size_outcomes.build(analysis_config, "all").collect().sort("size_band")

    assert result.select("size_band", "source_patches", "matches").to_dicts() == [
        {"size_band": "medium_21_100", "source_patches": 1, "matches": 1},
        {"size_band": "small_1_20", "source_patches": 4, "matches": 1},
    ]
