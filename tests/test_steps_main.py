import dataclasses

import pytest

from lkml_ground_truth import cli
from lkml_ground_truth.steps import main as steps_main
from lkml_ground_truth.steps import repo
from lkml_ground_truth.steps.main import STEP_NAMES, RunOptions, build_registry, run_steps


def _registry(calls, failing=()):
    def make(name):
        def run():
            calls.append(name)
            if name in failing:
                raise RuntimeError(name)

        return run

    return {name: make(name) for name in STEP_NAMES}


def test_registry_matches_declared_names(analysis_config):
    registry = build_registry(RunOptions(config=analysis_config))

    assert tuple(registry) == STEP_NAMES


def test_default_run_executes_every_step_in_order():
    calls = []

    assert run_steps(_registry(calls)) == 0
    assert calls == ["repo", "matching", "enrich"]


def test_all_is_same_as_no_selection():
    calls = []

    run_steps(_registry(calls), "all")

    assert calls == list(STEP_NAMES)


@pytest.mark.parametrize("selection", ["matching", "matching.py"])
def test_named_step_runs_alone(selection):
    calls = []

    assert run_steps(_registry(calls), selection) == 0
    assert calls == ["matching"]


def test_unknown_step_is_reported_and_runs_nothing():
    calls = []

    assert run_steps(_registry(calls), "nope") == 1
    assert calls == []


def test_failure_stops_later_steps():
    calls = []

    assert run_steps(_registry(calls, failing={"matching"})) == 1
    assert calls == ["repo", "matching"]  # enrich depends on matching, so it never ran


def test_named_step_errors_propagate():
    with pytest.raises(RuntimeError):
        run_steps(_registry([], failing={"matching"}), "matching")


@pytest.mark.parametrize(
    ("auto_clone", "force", "expected"),
    [(False, False, False), (False, True, True), (True, False, True)],
)
def test_repo_step_forces_clone_only_when_asked(
    analysis_config, monkeypatch, auto_clone, force, expected
):
    config = dataclasses.replace(
        analysis_config, repo=dataclasses.replace(analysis_config.repo, auto_clone=auto_clone)
    )
    seen = {}
    monkeypatch.setattr(
        repo,
        "ensure_repo",
        lambda repo_config, path: seen.update(auto_clone=repo_config.auto_clone),
    )

    repo.main(config, force=force)

    assert seen == {"auto_clone": expected}
    assert config.repo.auto_clone is auto_clone  # the loaded config is not mutated


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    def fake_run_steps(registry, selection=None):
        calls.append((selection, tuple(registry)))
        return 0

    monkeypatch.setattr(steps_main, "run_steps", fake_run_steps)
    return calls


@pytest.mark.parametrize(
    ("argv", "selection"),
    [
        ([], ""),
        (["run"], ""),
        (["run", "--step", "matching"], "matching"),
        (["clone-repo", "--force"], "repo"),
        (["enrich"], "enrich"),
    ],
)
def test_cli_dispatches_to_the_orchestrator(analysis_config, tmp_path, recorded, argv, selection):
    code = cli.main(["--config", str(tmp_path / "config.toml"), *argv])

    assert code == 0
    assert recorded == [(selection, STEP_NAMES)]
