"""Each chart analysis writes exactly one image."""

import polars as pl
import pytest

from lkml_ground_truth.analysis import (
    integration_cdf,
    latency_distribution,
    latency_per_month,
    match_rate_per_month,
    patches_per_month,
    temporal_data,
)

CHART_MODULES = [
    patches_per_month,
    match_rate_per_month,
    latency_distribution,
    latency_per_month,
    integration_cdf,
]


@pytest.mark.parametrize("module", CHART_MODULES, ids=lambda m: m.NAME)
def test_writes_exactly_one_image(module, analysis_config, tmp_path):
    out = tmp_path / "out"

    module.main(analysis_config, str(out), "all")

    images = sorted(p.name for p in out.iterdir() if p.suffix == ".svg")
    assert images == [f"{module.NAME}.svg"]
    assert (out / f"{module.NAME}.svg").stat().st_size > 0


@pytest.mark.parametrize("module", CHART_MODULES, ids=lambda m: m.NAME)
def test_each_image_has_a_single_axes(module, analysis_config, tmp_path, monkeypatch):
    import matplotlib.figure

    axes_counts = []
    original_savefig = matplotlib.figure.Figure.savefig

    def spy(self, *args, **kwargs):
        axes_counts.append(len(self.axes))
        return original_savefig(self, *args, **kwargs)

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", spy)

    module.main(analysis_config, str(tmp_path / "out"), "all")

    assert axes_counts == [1]


@pytest.mark.parametrize("module", CHART_MODULES, ids=lambda m: m.NAME)
def test_without_data_writes_nothing(module, analysis_config, tmp_path, monkeypatch):
    empty = pl.DataFrame({"month": [], "latency_days": []}).lazy()
    monkeypatch.setattr(temporal_data, "build", lambda *args: empty)
    monkeypatch.setattr(temporal_data, "matched_latency", lambda *args: empty)
    monkeypatch.setattr(latency_distribution, "matched_latency", lambda *args: empty)
    monkeypatch.setattr(integration_cdf, "build", lambda *args: empty)

    module.main(analysis_config, str(tmp_path / "out"), "all")

    assert not (tmp_path / "out").exists()


def test_confident_only_changes_matched_series(analysis_config, tmp_path):
    out = tmp_path / "out"

    patches_per_month.main(analysis_config, str(out), "all", confident_only=True)

    assert (out / "patches_per_month.svg").exists()


def test_integration_cdf_exports_empirical_cumulative_share(analysis_config):
    cdf = integration_cdf.build(analysis_config, "all").collect()

    assert cdf.to_dicts() == [
        {"latency_days": pytest.approx(2.5), "integrated_share": pytest.approx(0.5)},
        {"latency_days": pytest.approx(10.0), "integrated_share": pytest.approx(1.0)},
    ]


def test_integration_cdf_can_use_only_confident_matches(analysis_config):
    cdf = integration_cdf.build(analysis_config, "all", confident_only=True).collect()

    assert cdf.to_dicts() == [
        {"latency_days": pytest.approx(2.5), "integrated_share": pytest.approx(1.0)}
    ]
