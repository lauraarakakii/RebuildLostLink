# RebuildLostLink Analysis

Reproducible analyses over the matching results: how many patch emails were linked to a commit, how reliable those links are, and how long patches take to be integrated.

## Overview

Each analysis is a small module that reads the `original` (MLH dataset) and `enriched` (matching results) Parquet tables, and writes its result to an output directory. An orchestrator runs every default analysis, or a single one by name. Data is handled with Polars lazy frames, so nothing is copied and large datasets stay manageable. The integration-time analyses make the linked email/commit pairs useful for empirical studies of Linux patch lifecycles.

```
┌─────────────────┐     ┌─────────────────┐
│    original     │     │    enriched     │
│  (MLH dataset)  │     │ (match results) │
└────────┬────────┘     └────────┬────────┘
         └──────────┬────────────┘
                    ▼
          ┌───────────────────┐     ┌──────────────────────────┐
          │   Orchestrator    │ ──► │ output/analysis/*.csv    │
          │ (analysis/main.py)│     │ output/analysis/*.svg    │
          └───────────────────┘     └──────────────────────────┘
```

## Prerequisites

### Container Runtime (Optional)
- Docker or Podman, used automatically when `uv` is not installed

### Native Development (Recommended)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

### Using Devbox (Recommended)

```bash
devbox shell
```

This sets up Python, uv and the other dependencies automatically.

### Manual Setup

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the repository root: install dependencies
uv sync --locked --group dev
```

## Usage

### Running Analyses

The analyses expect the pipeline to have run (`make run`, which also runs `make enrich`).

```bash
# Using Make (runs all default analyses)
make analysis

# Run a single analysis by name
make analysis ANALYSIS=score_bands
make analysis ANALYSIS=latency_per_month LIST=netdev
make analysis ANALYSIS=latency_per_month LIST=netdev,bpf CONFIDENT_ONLY=1

# Interactive SQL
make analysis ANALYSIS=sql_querier LIST=all
make analysis ANALYSIS=sql_querier LIST=netdev SQL='SELECT * FROM enriched LIMIT 10'

# Directly, without Make
uv run rebuild-lost-link --config config.toml analysis --analysis latency_per_month --list netdev
uv run python -m rebuild_lost_link.analysis --config config.toml
```

### Input/Output Directories

| Directory | Purpose |
|-----------|---------|
| `paths.dataset_root` | Input: MLH Parquet dataset (`list=<name>/*.parquet`), the `original` table |
| `paths.enriched_root` | Input: matching results (`list=<name>/data.parquet`), the `enriched` table |
| `output/analysis/` | Output: analysis results and figures (ignored by Git) |

## Available Analyses

### main.py

Orchestrator that runs all default analyses. A failure in one analysis is logged and does not stop the others, and the process exits with an error code at the end. Supports selecting a single analysis with `ANALYSIS` (or `--analysis`); names may carry a `.py` suffix. `all` is accepted and behaves like no selection.

```bash
# Run every default analysis
uv run rebuild-lost-link --config config.toml analysis

# Run a single analysis
uv run rebuild-lost-link --config config.toml analysis --analysis score_bands
```

### dataset_coverage.py

Pipeline coverage relative to all source emails: original emails, patches evaluated, matches, confident matches and errors, per list. Uses `original` and `enriched`.

### match_coverage.py

Coverage, confident matches, patches without a candidate commit, errors and mean score, per list.

### score_bands.py

How many patches fall in each decision of the pipeline: `confident_match`, `review_match`, `no_candidate` or `below_threshold`, with score statistics.

### match_errors.py

Candidate-search errors, grouped to diagnose systematic problems.

### commit_reuse.py

Commits linked to several emails of the same list; candidates for series, resends or false positives worth reviewing.

### matched_pairs.py

Matched email/commit pairs with both dates, useful to analyze integration latency and to validate individual cases.

### discussion_context.py

Joins thread metadata from `original` with match outcomes. It compares initial submissions with replies or revisions (emails carrying `in_reply_to` or `references`), enabling studies of how discussion context relates to integration.

### patch_size_outcomes.py

Joins the original patch text with match outcomes. It estimates changed lines from added and removed diff lines, then reports matching outcomes by size band. This supports analysis of whether patch complexity is associated with integration.

### Charts (one analysis = one chart = one image)

Five analyses study the results over time or by integration latency. Each one draws **a single chart** and saves **a single image**; the shared data queries live in `temporal_data.py` and the matplotlib helpers in `plotting.py` (neither is an analysis).

| Analysis | Image | CSV | What it shows |
|----------|-------|-----|---------------|
| `patches_per_month` | `patches_per_month.svg` | `patches_per_month.csv` | Evaluated patches vs. patches matched to a commit |
| `match_rate_per_month` | `match_rate_per_month.svg` | `match_rate_per_month.csv` | Share of evaluated patches with a match and with a confident match |
| `latency_distribution` | `latency_distribution.svg` | none | Distribution of `commit_date - email_date`, in days, up to P99, with the median |
| `latency_per_month` | `latency_per_month.svg` | `latency_per_month.csv` | Monthly median latency and interquartile range |
| `integration_cdf` | `integration_cdf.svg` | `integration_cdf.csv` | Empirical share of linked patches integrated by each elapsed time; supports direct comparison of 7-, 30- and 90-day integration rates across lists |

Use `CONFIDENT_ONLY=1` to restrict `patches_per_month`, `latency_distribution`, `latency_per_month` and `integration_cdf` to confident matches. Recent months naturally show lower match rates and shorter latencies, because their commits may not exist yet. Latency is also bounded by `matching.days_after`, and can be slightly negative since the candidate window starts `matching.days_before` days before the email date. The CDF is conditional on linked patches, so it describes observed integration time rather than a survival estimate for every submitted patch.

To add a new chart, create a module that exposes `main(config, output_dir, list_name)`, draw it with `plotting.new_chart()` / `plotting.save_chart()` (one axes per figure) and register it in `main.py`.

### sql_querier.py

Interactive SQL interface using [Apache DataFusion](https://datafusion.apache.org/user-guide/sql/index.html). Registers the `original` and `enriched` tables for the selected lists, shows their schemas and prompts for SQL queries. With `SQL`, it runs one query and exits. Results can be saved with `OUTPUT` (CSV, Parquet, JSON or NDJSON). This is a non-default analysis: it only runs when explicitly selected.

```bash
make analysis ANALYSIS=sql_querier
make analysis ANALYSIS=sql_querier SQL='SELECT list, count(*) FROM enriched GROUP BY list' OUTPUT=output/by_list.csv
```

## Output

Analysis results are stored in `output/analysis/`:

```
output/analysis/
├── dataset_coverage.csv
├── match_coverage.csv
├── score_bands.csv
├── match_errors.csv
├── commit_reuse.csv
├── matched_pairs.csv
├── discussion_context.csv
├── patch_size_outcomes.csv
├── patches_per_month.csv
├── patches_per_month.svg
├── match_rate_per_month.csv
├── match_rate_per_month.svg
├── latency_distribution.svg
├── latency_per_month.csv
├── latency_per_month.svg
├── integration_cdf.csv
└── integration_cdf.svg
```

`commit_date` is the Git *committer* date, in ISO 8601. It is only present in pipeline runs made after this column was added, so temporal analyses need a recent run.

## Configuration

Paths come from `config.toml` (`paths.dataset_root`, `paths.enriched_root`). Everything else is selected with Make variables or CLI options.

### Make Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANALYSIS` | *(empty)* | Run a single analysis by name instead of all default ones. Valid names: `dataset_coverage`, `match_coverage`, `score_bands`, `match_errors`, `commit_reuse`, `matched_pairs`, `discussion_context`, `patch_size_outcomes`, `patches_per_month`, `match_rate_per_month`, `latency_distribution`, `latency_per_month`, `integration_cdf`, `sql_querier`†. († non-default, only runs when explicitly selected) |
| `LIST` | `all` | Mailing list(s) to analyze: a name, a comma-separated list (`netdev,bpf`) or `all` |
| `RESULTS_DIR` | `output/analysis` | Directory for analysis output |
| `CONFIG` | `config.toml` | Configuration file |

### Per-Analysis Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIDENT_ONLY` | *(empty)* | Set to `1` to use only confident matches for latency. Used by: `patches_per_month`, `latency_distribution`, `latency_per_month`, `integration_cdf` |
| `SQL` | *(empty)* | SQL to run once and exit; omit for the interactive REPL. Used by: `sql_querier` |
| `OUTPUT` | *(empty)* | File to save the SQL result to. Used by: `sql_querier` |
| `FORMAT` | *(inferred)* | `csv`, `parquet`, `json` or `ndjson`; inferred from `OUTPUT` when omitted. Used by: `sql_querier` |
| `LIMIT` | `20` | Terminal row limit, `0` shows all. Used by: `sql_querier` |

### CLI Options

The same options are available as `uv run rebuild-lost-link --config config.toml analysis [options]`:

| Option | Description |
|--------|-------------|
| `-a, --analysis <NAME>` | Analysis to run (default: all default analyses) |
| `-l, --list <NAMES>` | List name, comma-separated names, or `all` (default) |
| `-o, --output-dir <DIR>` | Output directory (default: `output/analysis`) |
| `--confident-only` | `patches_per_month`, `latency_distribution`, `latency_per_month`, `integration_cdf`: confident matches only |
| `--sql <SQL>` | `sql_querier`: query to run once |
| `--sql-output <PATH>` | `sql_querier`: save the result |
| `--sql-format <FMT>` | `sql_querier`: output format |
| `--limit <N>` | `sql_querier`: terminal row limit |

## Development

### Running Natively

For development and debugging, run the orchestrator directly from the repository root:

```bash
# Run all default analyses
uv run python -m rebuild_lost_link.analysis --config config.toml

# Run a single analysis, with a custom output directory
uv run python -m rebuild_lost_link.analysis --config config.toml \
  --analysis latency_per_month --list netdev --output-dir /tmp/lkml-analysis
```

### Tests and Lint

```bash
make test
make lint
```

## Container Build

When `uv` is not installed, `make analysis` runs inside the project container (`docker` or `podman`) using the same arguments, mounting the repository and the dataset volumes. Rebuild the image with:

```bash
make rebuild
```

## Example Analysis Code

Here is an example of querying the matching results with Polars:

```python
import polars as pl

# Load the enriched dataset (one list=<name> partition per mailing list)
df = pl.scan_parquet("output/enriched/list=netdev/*.parquet")

# Confident matches per commit date
per_day = (
    df
    .filter(pl.col("is_confident_match"))
    .with_columns(
        pl.col("commit_date").str.to_datetime(time_zone="UTC").dt.date().alias("day")
    )
    .group_by("day")
    .agg(pl.len().alias("matches"))
    .sort("day")
    .collect()
)
```

Inside the package, prefer `scan_original(config, list_name)` and `scan_enriched(config, list_name)` from `datasets.py`: they select the requested lists and normalize column types (for example, `score` to `Float64`).

## Cleaning Up

```bash
# Remove build artifacts (not results)
make clean

# This removes:
# - .venv/
# - .ruff_cache/
# - .nox/
# - __pycache__/
```

## Troubleshooting

### "Dataset directory does not exist" / "No Parquet files found"
Check `paths.dataset_root` and `paths.enriched_root` in `config.toml`, and run the pipeline first:
```bash
make run
```

### Some analyses failed
Each failure is logged with its traceback and the other analyses still run. Re-run the failing one on its own to debug it:
```bash
make analysis ANALYSIS=<name>
```

### Memory Issues
For large datasets:
- Use Polars lazy evaluation (`scan_parquet` instead of `read_parquet`)
- Filter data early in the query pipeline
- Restrict the lists with `LIST=netdev,bpf`

## Extending Analyses

To add a new analysis:

1. Create a module in this folder with a `build(config, list_name)` function returning a `pl.LazyFrame`, and a `main(config, output_dir, list_name="all")` that saves the result (see `score_bands.py`; `common.write_csv` writes `<name>.csv`).
2. Register it in `main.py`: add its name to `ANALYSIS_NAMES` and a lambda to `build_registry()`. Add it to `NON_DEFAULT_ANALYSES` if it should only run when selected.
3. Add a test in `tests/` (the `analysis_config` fixture provides a small dataset).
4. Document it in this README.

Example:

```python
# src/rebuild_lost_link/analysis/my_analysis.py
import polars as pl

from ..config import Config
from .common import write_csv
from .datasets import scan_enriched


def build(config: Config, list_name: str) -> pl.LazyFrame:
    return scan_enriched(config, list_name).group_by("list").agg(pl.len().alias("patches"))


def main(config: Config, output_dir: str, list_name: str = "all") -> None:
    write_csv(build(config, list_name), output_dir, "my_analysis")
```

## License

See the root [LICENSE](../../../LICENSE) file.
