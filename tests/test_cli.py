from rebuild_lost_link import cli


def test_default_command_runs_every_step_in_order(monkeypatch):
    calls = []
    for name in cli.STEPS:
        monkeypatch.setitem(cli.STEPS, name, lambda config, n=name: calls.append(n))
    monkeypatch.setattr(cli, "load_config", lambda path: object())

    assert cli.main([]) == 0
    assert calls == ["repo", "match", "enrich"]


def test_run_stops_at_first_failure(monkeypatch):
    calls = []

    def fail(config):
        raise RuntimeError("boom")

    monkeypatch.setitem(cli.STEPS, "repo", fail)
    monkeypatch.setitem(cli.STEPS, "match", lambda config: calls.append("match"))
    monkeypatch.setattr(cli, "load_config", lambda path: object())

    assert cli.main(["run"]) == 1
    assert calls == []


def test_analyze_forwards_arguments(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "load_config", lambda path: "config")
    monkeypatch.setattr(cli.analysis, "run", lambda *args: seen.update(args=args) or 0)

    assert cli.main(["analyze", "coverage", "-l", "iio", "-o", "out"]) == 0
    assert seen["args"] == ("config", ["coverage"], "iio", "out")
