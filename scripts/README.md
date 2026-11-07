# Validation scripts

Three stand-alone scripts for the manual inspection protocol. They take finished artifacts as
input and never modify the LKML5Ws dataset. Plotting needs `uv sync --group plots`.

## 1. Export list A from a Linux clone

JSON Lines (one commit per line, with `commit_id` and `diff`) keeps multi-line diffs intact.

```bash
python scripts/extract_kernel_diffs.py \
  --repo /path/to/linux \
  --ref master \
  --since 2026-01-01 --until 2026-06-30 \
  --output output/list_a_kernel.jsonl
```

To restrict the export, put one commit hash per line in `commits.txt` and add
`--commit-list commits.txt`. Commits in the period are found with
`git log --format=%H --no-renames --since=... --until=... <ref>`, and each diff with `git show`.

## 2. Integrate A, B and C

- **B**: CSV with header `message_id,diff` (quote diffs that contain commas or newlines).
- **C**: the match CSV from the main pipeline, or Parquet; `best_commit` is accepted as an alias
  of `commit_hash`.

Only rows of C with `is_match=true` are integrated unless `--include-non-matches` is given.

```bash
python scripts/integrate_lists.py \
  --git-list output/list_a_kernel.jsonl \
  --lkml-list /path/to/list_b.csv \
  --correlation output/matches.csv \
  --output output/integrated.jsonl
```

The output has `message_id`, `commit_hash`, `github_diff` and `lkml_diff`.

## 3. Review in the browser

```bash
python scripts/review_server.py \
  --integrated output/integrated.jsonl \
  --responses output/review_responses.csv \
  --reviewer laura
```

Open `http://localhost:8000`. From a phone on the same network, use
`http://<computer-ip>:8000` (the server listens on `0.0.0.0` by default; pass `--host 127.0.0.1`
for local access only, and do not expose the port to the internet). Each click is appended to the
responses CSV and flushed to disk. Restarting with the same `--reviewer` skips answered
`message_id`s.

## 4. Plot patch-size results

```bash
uv run rebuild-lost-link analyze patch_size_outcomes
uv run python scripts/plot_patch_size_outcomes.py output/analysis/patch_size_outcomes.csv
```
