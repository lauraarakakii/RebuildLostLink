from datetime import UTC, datetime
from types import SimpleNamespace

import rebuild_lost_link.engine as engine


def _run(monkeypatch, similarity):
    commit_date = datetime(2026, 9, 27, 10, 30, tzinfo=UTC)
    message_diff = SimpleNamespace(
        message=["subject"],
        diff=SimpleNamespace(affected=["a", "b"], lines=3, raw=["@@ -1 +1 @@"]),
    )
    commit = SimpleNamespace(
        message=["subject"],
        diff=SimpleNamespace(),
        committer=SimpleNamespace(date=commit_date),
    )

    monkeypatch.setattr(
        engine,
        "_config",
        SimpleNamespace(matching=SimpleNamespace(days_before=3, days_after=365)),
    )
    monkeypatch.setattr(
        engine,
        "_thresholds",
        SimpleNamespace(interactive=0.5, autoaccept=0.8, message_diff_weight=0.5),
    )
    monkeypatch.setattr(engine, "_repo", {"abcdef": commit})
    monkeypatch.setattr(engine, "_index", {})
    monkeypatch.setattr(engine, "row_to_messagediff", lambda row: message_diff)
    monkeypatch.setattr(engine, "find_candidates", lambda *args: {"abcdef"})
    monkeypatch.setattr(
        engine,
        "evaluate_patch_pair",
        lambda *args: SimpleNamespace(msg=similarity, diff=similarity),
    )

    return engine.process_row({"message_id": "message@example.com", "date": commit_date})


def test_process_row_includes_selected_commit_committer_date(monkeypatch):
    result = _run(monkeypatch, 1.0)

    assert result["best_commit"] == "abcdef"
    assert result["commit_date"] == "2026-09-27T10:30:00+00:00"
    assert (result["file_size"], result["line_size"], result["hunk_size"]) == (2, 3, 1)


def test_process_row_links_no_commit_below_the_threshold(monkeypatch):
    result = _run(monkeypatch, 0.2)

    assert result["score"] == 0.2
    assert result["is_match"] is False
    assert result["best_commit"] is None
    assert result["commit_date"] is None
