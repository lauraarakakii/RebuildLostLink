# Analysis

This folder holds reproducible analyses over the matching results. Each
function in `fixed.py` answers one specific question with Polars Lazy and
writes a CSV to `output/analysis/`, a directory ignored by Git.

It uses the same query context as the rest of the project, so it reads the
`original` and `enriched` Parquet tables defined in `config.toml` without
making copies of the datasets.

## Running

After running the pipeline (`make run`, which also runs `make enrich`):

```bash
# From the repository root
make analysis ANALYSIS=dataset_coverage LIST=all

# Or directly from this folder
make -C src/lkml_ground_truth/analysis run ANALYSIS=commit_reuse LIST=netdev
```

## Interactive SQL queries

`sql_querier.py` is this folder's query entry point, equivalent to the
analysis component of MLH-Archiver. Without SQL it opens a REPL; with SQL it
runs a single query:

```bash
make analysis ANALYSIS=sql_querier.py LIST=all
make analysis ANALYSIS=sql_querier.py LIST=netdev SQL='SELECT * FROM enriched LIMIT 10'
```

It is an interface to the same query context as the rest of the project, so
the available tables are `original` and `enriched`.

Use `make -C src/lkml_ground_truth/analysis help` to list the analyses. To use
another configuration file or a different destination for the CSVs:

```bash
make -C src/lkml_ground_truth/analysis run ANALYSIS=score_bands \
  CONFIG=/path/to/config.toml RESULTS_DIR=/tmp/lkml-analysis
```

## Available fixed analyses

| Analysis | What it reveals |
| --- | --- |
| `dataset_coverage` | Pipeline coverage relative to all emails: original source, patches evaluated, matches, confident matches and errors. Uses `original` and `enriched`. |
| `match_coverage` | Coverage, confident matches, missing candidates, errors and mean score per list. |
| `score_bands` | How many patches fall in each pipeline decision: confident, needs review, no candidate or below threshold. |
| `match_errors` | Candidate-search errors, grouped to help diagnose systematic problems. |
| `commit_reuse` | Commits linked to several emails; candidates for series, resends or false positives worth reviewing. |
| `matched_pairs` | Email/commit pairs with both dates, useful for analyzing integration latency and validating individual cases. |

`commit_date` is the Git *committer* date, in ISO 8601. For temporal
analyses, it is only present in pipeline runs made after this column was
added.

## Temporal analysis (figure)

`temporal.py` studies the results over time, by month of the patch email date,
using Polars for the data and Matplotlib for the figure:

```bash
make analysis ANALYSIS=temporal LIST=all
make analysis ANALYSIS=temporal LIST=netdev CONFIDENT_ONLY=1
```

It writes `output/analysis/temporal.png` and a monthly summary,
`output/analysis/temporal.csv`. The figure has four panels:

| Panel | What it shows |
| --- | --- |
| Patches per month | Evaluated patches vs. patches matched to a commit |
| Match rate per month | Share of evaluated patches with a match and with a confident match |
| Integration latency | Distribution of `commit_date - email_date`, in days, with the median |
| Integration latency per month | Monthly median and interquartile range |

`CONFIDENT_ONLY=1` restricts the latency panels to confident matches. It can
also be run directly: `uv run python -m lkml_ground_truth.analysis.temporal --help`.

Reading the figure: recent months naturally show lower match rates and shorter
latencies, because their commits may not exist yet. Latency is also bounded by
`matching.days_after`, and can be slightly negative since the candidate window
starts `matching.days_before` days before the email date.

## Adding a finding

1. Create a function in `fixed.py`, using `scan_original()` and/or `scan_enriched()`.
2. Document the question and how to interpret the result in the table above.
3. Add the function to `ANALYSES`, run `make analysis ANALYSIS=<name>` and keep the code in Git;
   the resulting CSV lives in `output/analysis/`.