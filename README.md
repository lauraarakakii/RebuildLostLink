# RebuildLostLink

Links Linux kernel patch emails to the commits that integrate them, producing a dataset of
"which email became which commit".

Input is the [LKML5Ws](https://gitlab.com/ccsl-usp/codev/MailingListsHeritage) Parquet dataset
(built by MailingListsHeritage) and a clone of the Linux Git repository. Patch comparison reuses a
vendored subset of [PaStA](https://github.com/lfd/PaStA); a persistent file-to-commit index limits
each email to the few commits that touch the same files in a time window.

```
LKML5Ws Parquet ──► match (CSV per list) ──► enrich (Parquet per list) ──► analyze (CSV reports)
                        ▲
                Linux Git repo + file index
```

## Install

```bash
uv sync --locked --group dev     # add --group plots to draw figures with scripts/
```

Without `uv`, build the image (`make image`); `make` targets then run inside the container.

## Configure

```bash
make config      # copies example_config.toml to config.toml
```

Set at least `paths.dataset_root` (contains `list=<name>/*.parquet`), `paths.repo_path` and
`paths.list_name` (one list, or `all`). Matching parameters live in `[matching]`:

| Key | Default | Meaning |
|-----|---------|---------|
| `days_before` / `days_after` | 3 / 365 | candidate commit window around the email date |
| `autoaccept` | 0.8 | score at or above which a match is confident |
| `interactive` | 0.5 | score at or above which a match is reported (needs review) |
| `message_diff_weight` | 0.5 | weight of the message score vs. the diff score |

To let the tool clone the kernel, set `repo.auto_clone = true`. With `repo.since` the clone is
shallow, so it must start before the oldest patch you want to match.

## Run

```bash
make run                                   # repo -> match -> enrich
uv run rebuild-lost-link match             # a single step: repo | match | enrich
make analyze NAMES="coverage" LISTS=iio    # analysis CSVs in output/analysis/
```

Matching resumes from checkpoints after an interruption. Keep `performance.parallel_lists = 1`
unless the host has plenty of memory: processes are `parallel_lists × num_workers`.

## Output

One row per patch email, in `output/matches_<list>.csv` and `output/enriched/list=<name>/data.parquet`:

| Column | Description |
|--------|-------------|
| `message_id` | email identifier in LKML5Ws |
| `best_commit` | hash of the best-scoring candidate commit |
| `commit_date` | committer timestamp (`timestamp[us]`, UTC, in the Parquet) |
| `file_size`, `line_size`, `hunk_size` | files, added/removed lines and hunks in the patch |
| `score` | similarity, 0.0 to 1.0 |
| `is_match` | `score >= matching.interactive` |
| `is_confident_match` | `score >= matching.autoaccept` |
| `error` | processing error, when any |

## Analyses

`rebuild-lost-link analyze [names] [-l lists] [-o dir]` writes one CSV per analysis. Each is a
function `(config, lists) -> LazyFrame` in `src/rebuild_lost_link/analysis/`:

| Name | Module | Answers |
|------|--------|---------|
| `coverage` | `quality` | source emails vs. evaluated, matched, errored; mean score |
| `score_bands` | `quality` | patches by decision (confident, review, below threshold, no candidate) |
| `match_errors` | `quality` | processing errors, grouped |
| `commit_reuse` | `quality` | commits linked to several emails |
| `patch_size_outcomes` | `patch_size` | match rate by patch-size band |
| `patch_size_outcomes_by_sender` | `patch_size` | same, split by sender type |
| `integration_latency` | `latency` | quartiles and share integrated within 7/30/90 days |

The study window (email dates from May 2016 to May 2026) is `STUDY_START`/`STUDY_END` in
`analysis/data.py`. To add an analysis, write the function and add it to `ANALYSES` in
`analysis/__init__.py`.

## Validation scripts

`scripts/` holds stand-alone utilities for the manual inspection protocol (export commit diffs,
join emails, commits and matches, review pairs in a browser, plot patch-size results). See
[scripts/README.md](scripts/README.md).

## Layout

```
src/rebuild_lost_link/
  cli.py          command line
  config.py       config.toml model
  repo_setup.py   clone / validate the kernel repository
  commit_index.py persistent file-to-commit index
  engine.py       patch-to-commit comparison for one email
  pipeline.py     matching over lists (workers, checkpoints)
  enrich.py       CSV -> Parquet
  analysis/       data.py, quality.py, patch_size.py, latency.py
  pasta/          vendored PaStA subset (upstream license)
tests/            pytest
```

`make test` and `make lint` run the test suite and ruff.

## License

See [LICENSE](LICENSE). The vendored `pasta/` subpackage keeps its upstream PaStA copyright and GPLv2 notices.
