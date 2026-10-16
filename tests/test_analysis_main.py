import pytest

from lkml_ground_truth.analysis import main as analysis_main
from lkml_ground_truth.analysis.main import ANALYSIS_NAMES, RunOptions, build_registry, run_analyses


def _registry(calls, failing=()):
    def make(name):
        def run():
            calls.append(name)
            if name in failing:
                raise RuntimeError(name)

        return run

    return {name: make(name) for name in ANALYSIS_NAMES}


def test_registry_matches_declared_names(analysis_config):
    registry = build_registry(RunOptions(config=analysis_config))

    assert tuple(registry) == ANALYSIS_NAMES


def test_default_run_skips_non_default_analyses():
    calls = []

    failures = run_analyses(_registry(calls))

    assert failures == 0
    assert calls == [n for n in ANALYSIS_NAMES if n != "sql_querier"]


def test_all_is_same_as_no_selection():
    calls = []

    run_analyses(_registry(calls), "all")

    assert "sql_querier" not in calls
    assert len(calls) == len(ANALYSIS_NAMES) - 1


@pytest.mark.parametrize("selection", ["score_bands", "score_bands.py"])
def test_named_analysis_runs_alone(selection):
    calls = []

    assert run_analyses(_registry(calls), selection) == 0
    assert calls == ["score_bands"]


def test_non_default_analysis_runs_when_selected():
    calls = []

    run_analyses(_registry(calls), "sql_querier.py")

    assert calls == ["sql_querier"]


def test_unknown_analysis_is_reported_and_runs_nothing():
    calls = []

    assert run_analyses(_registry(calls), "nope") == 1
    assert calls == []


def test_one_failure_does_not_stop_the_others():
    calls = []

    failures = run_analyses(_registry(calls, failing={"score_bands"}))

    assert failures == 1
    assert "latency_per_month" in calls  # ran after the failing analysis


def test_named_analysis_errors_propagate():
    with pytest.raises(RuntimeError):
        run_analyses(_registry([], failing={"score_bands"}), "score_bands")


def test_cli_runs_every_default_analysis_end_to_end(analysis_config, tmp_path):
    out = tmp_path / "results"
    config_path = tmp_path / "config.toml"

    code = analysis_main.main(["--config", str(config_path), "--output-dir", str(out)])

    assert code == 0
    produced = {p.name for p in out.iterdir()}
    charts = (
        "patches_per_month",
        "match_rate_per_month",
        "latency_distribution",
        "latency_per_month",
        "integration_cdf",
    )
    expected = {f"{n}.csv" for n in ANALYSIS_NAMES if n not in ("sql_querier", *charts)}
    assert expected <= produced
    # one chart per analysis: exactly one image each
    assert {f"{n}.svg" for n in charts} <= produced
    assert len({p for p in produced if p.endswith(".svg")}) == len(charts)


def test_cli_limits_to_comma_separated_lists(analysis_config, tmp_path):
    out = tmp_path / "results"

    code = analysis_main.main(
        [
            "--config",
            str(tmp_path / "config.toml"),
            "--output-dir",
            str(out),
            "--analysis",
            "dataset_coverage",
            "--list",
            "netdev, missing",
        ]
    )

    # "missing" has no data and is skipped; netdev is still analyzed.
    assert code == 0
    assert (out / "dataset_coverage.csv").exists()
