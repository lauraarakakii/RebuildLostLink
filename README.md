# LKML Ground Truth - Link Linux Kernel Patch Emails to Their Commits

Match patch emails from a [MailingListsHeritage](https://gitlab.com/ccsl-usp/codev/MailingListsHeritage) (MLH) Parquet dataset to the commits that integrate them into a Linux Git repository, producing a ground truth of "which email became which commit".

This software reuses a vendored subset of [PaStA](https://github.com/lfd/PaStA) for patch comparison and a persistent file-to-commit index for candidate discovery, so each email is compared only against the few commits that touch the same files in a relevant time window.

## Pipeline Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  MLH Dataset    │ ──► │    Matching     │ ──► │     Enrich      │ ──► │    Analysis     │
│ (Parquet input) │     │ (CSV per list)  │     │ (Parquet output)│     │  (CSV / SQL)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
                                ▲
                                │
                        ┌───────┴───────┐
                        │ Linux Git repo│
                        │ + file index  │
                        └───────────────┘
```

## Project Components

This project consists of four main components:

| Component | Description | Language |
|-----------|-------------|----------|
| **[Matching Pipeline](src/lkml_ground_truth/)** | Compares each patch email with candidate commits and writes one CSV of matches per mailing list | Python |
| **[Enrichment](src/lkml_ground_truth/enrich.py)** | Persists the match results as Parquet partitioned by mailing list | Python |
| **[Analysis](src/lkml_ground_truth/analysis/)** | One module per analysis (Polars reports, a temporal figure and an interactive DataFusion SQL REPL), run by a single orchestrator | Python |
| **[Extra Scripts](scripts/)** | Stand-alone export, integration and manual review utilities | Python |

Each component has its own detailed documentation:

- [Analysis Documentation](src/lkml_ground_truth/analysis/README.md)
- [Scripts Documentation](scripts/README.md)

## Outputs

Each processed patch produces one row with:

| Column | Description |
|--------|-------------|
| `message_id` | Email identifier from the MLH dataset |
| `best_commit` | Hash of the best-scoring candidate commit |
| `commit_date` | Git committer timestamp, in ISO 8601 |
| `score` | Similarity score (0.0 to 1.0) |
| `is_match` | `true` when `score >= matching.interactive` |
| `is_confident_match` | `true` when `score >= matching.autoaccept` |
| `error` | Optional error message (e.g. candidate search failure) |

---
## Quick Start

### Step 1: Install

```bash
uv sync --locked --group dev
```

See [Development](#development) for the other setup options (Devbox, manual, Dev Container).

### Step 2: Configuring

1. Copy the example configuration file:

```bash
make config
```

or manually copy:

```bash
cp example_config.toml config.toml
```

2. Edit `config.toml`. At minimum, set where the MLH dataset and the Linux clone are:

```toml
[paths]
repo_path    = "resources/linux/repo"             # existing Linux clone (or clone destination)
dataset_root = "/path/to/mlh/output/parser/dataset" # contains list=<name>/*.parquet
list_name    = "netdev"                           # a single list, or "all"
```

#### Repository Examples

```toml
# Use an existing clone: just point paths.repo_path to it.

# Or let the tool clone it for you:
[repo]
auto_clone = true
clone_url  = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
since      = "2024-01-01"   # optional shallow clone lower bound; empty = full history
```

> [!WARNING]
> **`repo.since` must be early enough for your matching window.**
> Commits older than `since` do not exist in a shallow clone, so patches integrated before that date can never be matched.

#### Matching Examples

```toml
[matching]
days_before = 3      # candidate commits from 3 days before the email date...
days_after  = 365    # ...up to 365 days after it
autoaccept  = 0.8    # score >= 0.8 -> confident match
interactive = 0.5    # score >= 0.5 -> match (worth reviewing)
message_diff_weight = 0.5   # weight of the message score vs. the diff score
```

#### Performance Examples

```toml
[performance]
num_workers      = 0     # 0 = all CPU cores except one
parallel_lists   = 1     # lists processed concurrently (needs more RAM/CPU if > 1)
checkpoint_every = 200   # rows between checkpoints (resume after interruption)
rebuild_index    = false # true forces a rebuild of the commit index
```

> [!WARNING]
> **Keep `parallel_lists = 1` unless the host has plenty of memory and CPU.**
> Total processes are `parallel_lists × workers per list`, and every worker opens the Linux repository.

### Step 3: Run the Pipeline

```bash
make run        # run every step in order: repo -> matching -> enrich
make analysis   # run every default analysis
```

`make run` is made of three steps. Run just one with `STEP=<name>`:

| Step | What it does |
|------|--------------|
| `repo` | Validates the Linux clone at `paths.repo_path`, cloning it when `repo.auto_clone` is true |
| `matching` | Links each patch email to its best commit, writing one CSV per list |
| `enrich` | Persists the match CSVs as Parquet partitioned by list |

```bash
make run STEP=matching   # only the matching
make run STEP=enrich     # re-run only the enrichment
make repo                # clone the repository even when auto_clone is false
```

The steps depend on each other, so if one fails the run stops there instead of continuing.

The first `make run` builds the file-to-commit index in a single `git log --name-only` pass over the whole repository (a few minutes on the full kernel history) and caches it at `paths.commit_index_cache`. Later runs reuse it.

Long runs are resumable: partial results are checkpointed next to the output CSV and picked up automatically if the run is interrupted.

---

## Development

### Setup Options

You have three options for setting up the development environment:

#### Option 1: Devbox (Recommended)

[Devbox](https://www.jetify.com/devbox/) creates an isolated development shell using Nix packages. It provides all required dependencies in a single command.

**Installation:** See the [Devbox installation guide](https://www.jetify.com/docs/devbox/quickstart).

**Setup:**

```bash
devbox shell
```

This sets up:

- Python 3.12
- uv package manager
- Git and libgit2
- Ruff and prek (pre-commit hooks, installed automatically)

**Available Commands:**

| Command | Description |
|---------|-------------|
| `devbox run config` | Create `config.toml` from the example |
| `devbox run repo` | Clone or validate the Linux repository |
| `devbox run run` | Run patch-email to commit matching |
| `devbox run test` | Run all tests |
| `devbox run lint` | Run static checks |
| `devbox run fmt` | Format the code |
| `devbox run rebuild` | Rebuild the container image |
| `devbox run clean` | Clean local artifacts |

#### Option 2: Manual Installation

Install the required toolchain manually:

**Python/uv:**
Python 3.12 or newer, plus the uv package manager:
<https://docs.astral.sh/uv/getting-started/installation/>

**Git:**
Git and `libgit2` (needed by `pygit2`).

#### Option 3: Dev Container

This repository includes a [`.devcontainer`](.devcontainer/) configuration for VS Code or other compatible editors.

**Usage:**

1. Open the project in your editor (that supports devcontainer)
2. Click "Reopen in Container" when prompted
3. The dev container will build automatically

---

### Makefile Commands

The root [`Makefile`](Makefile) orchestrates the whole project. Run commands from the project root:

| Command | Description |
|---------|-------------|
| `make` or `make all` | Run the matching pipeline |
| `make config` | Create `config.toml` from `example_config.toml` |
| `make repo` | Clone the Linux repository (even when `repo.auto_clone` is false) or validate it |
| `make run` | Run every step in order: `repo` -> `matching` -> `enrich` |
| `make run STEP=<name>` | Run a single step (`repo`, `matching` or `enrich`) |
| `make enrich` | Re-run only the enrichment (same as `make run STEP=enrich`) |
| `make analysis` | Run every default analysis over all lists, saving results to `output/analysis/` |
| `make analysis ANALYSIS=<name> LIST=<names>` | Run a single analysis; `LIST` takes a name, a comma-separated list or `all` |
| `make analysis ANALYSIS=sql_querier LIST=<names>` | Open the interactive DataFusion SQL REPL |
| `make analysis ANALYSIS=sql_querier SQL='...'` | Run a single SQL query and exit |
| `make test` | Run all tests (via nox) |
| `make lint` | Run static checks (ruff) |
| `make fmt` | Format the code (ruff) |
| `make rebuild` | Rebuild the container image |
| `make clean` | Clean local artifacts |

Use `CONFIG=path/to/file.toml` with any command to select another configuration file.

---

## Container Runtime Configuration

Every command runs natively when [`uv`](https://docs.astral.sh/uv/) is installed. Otherwise, the Makefile falls back to a container, automatically using the first runtime found in `PATH` (`docker`, then `podman`). Containers run as your own user, never as root.

**Mounted volumes:**

| Variable | Default | Mounted at |
|----------|---------|------------|
| `REPO_VOLUME` | `./resources/linux/repo` | `/app/resources/linux/repo` |
| `DATASET_VOLUME` | `./resources/dataset` | `/app/resources/dataset` |

**Override the detected runtime or volumes:**

```bash
# Use podman explicitly
make run CONTAINER=podman

# Use datasets stored elsewhere
make run DATASET_VOLUME=/data/mlh/dataset REPO_VOLUME=/data/linux
```

> [!NOTE]
> When running inside the container, set `paths.repo_path` and `paths.dataset_root` in `config.toml` to the mounted locations (e.g. `resources/linux/repo` and `resources/dataset`).

---

## Utility Scripts

Independent from the main pipeline, the [`scripts/`](scripts/) directory has three utilities to cross-check the results against the kernel's own history and validate matches by hand. They take already-generated artifacts and never modify the MLH dataset. See the [Scripts Documentation](scripts/README.md) for the full guide.

### extract_kernel_diffs

Exports the diff of every commit in a period from a Linux clone as JSON Lines (one `commit_id` + `diff` per line).

```bash
python scripts/extract_kernel_diffs.py \
  --repo /path/to/linux \
  --ref master \
  --since 2026-01-01 --until 2026-06-30 \
  --output output/list_a_kernel.jsonl
```

| Option | Description |
|--------|-------------|
| `--repo <PATH>` | **Required.** Local Linux clone |
| `--output <PATH>` | **Required.** Output `.jsonl` file |
| `--ref <REF>` | Ref to walk (default: `HEAD`) |
| `--since <DATE>` / `--until <DATE>` | Date bounds accepted by Git |

### integrate_lists

Joins three lists into a single file: **A** (kernel commits and diffs), **B** (LKML emails and diffs) and **C** (the pipeline's match results).

```bash
python scripts/integrate_lists.py \
  --git-list output/list_a_kernel.jsonl \
  --lkml-list /path/to/list_b.csv \
  --correlation output/matches.csv \
  --output output/integrated.jsonl
```

| Option | Description |
|--------|-------------|
| `--git-list <PATH>` | **Required.** List A, JSONL from `extract_kernel_diffs` |
| `--lkml-list <PATH>` | **Required.** List B, CSV with `message_id,diff` |
| `--correlation <PATH>` | **Required.** List C, CSV or Parquet (`best_commit` is accepted as an alias of `commit_hash`) |
| `--output <PATH>` | **Required.** Integrated list (`.jsonl` recommended) |
| `--include-non-matches` | Do not restrict C to rows with `is_match=true` |

### review_server

Small web server to manually validate integrated pairs, from desktop or phone.

```bash
python scripts/review_server.py \
  --integrated output/integrated.jsonl \
  --responses output/review_responses.csv \
  --reviewer laura
```

Open `http://localhost:8000`. Each answer is saved immediately to an append-only CSV; restarting with the same `--reviewer` skips already-reviewed `message_id`s.

| Option | Description |
|--------|-------------|
| `--integrated <PATH>` | **Required.** Integrated list from `integrate_lists` |
| `--reviewer <NAME>` | **Required.** Reviewer identifier |
| `--responses <PATH>` | Responses CSV (default: `output/review_responses.csv`) |
| `--host <HOST>` | Bind address (default: `0.0.0.0`; use `127.0.0.1` for local-only) |
| `--port <PORT>` | Port (default: `8000`) |

> [!WARNING]
> **Do not expose the review server directly to the internet.** It listens on all interfaces by default.

---

## Analysis

Reproducible analyses over the matching results live in [`src/lkml_ground_truth/analysis/`](src/lkml_ground_truth/analysis/). Run them after `make run` (which already runs `make enrich`):

```bash
# Every default analysis, results in output/analysis/
make analysis

# A single analysis, for one or more lists
make analysis ANALYSIS=commit_reuse LIST=netdev
make analysis ANALYSIS=temporal LIST=netdev,bpf CONFIDENT_ONLY=1

# Interactive SQL REPL over the 'original' and 'enriched' tables
make analysis ANALYSIS=sql_querier LIST=all

# One-off SQL query
make analysis ANALYSIS=sql_querier LIST=netdev SQL='SELECT * FROM enriched LIMIT 10'
```

An analysis that fails is logged and does not stop the others. `sql_querier` is the only non-default analysis: it runs only when selected.

| Analysis | What it reveals |
|----------|-----------------|
| `dataset_coverage` | Pipeline coverage versus all emails: patches evaluated, matches, confident matches and errors |
| `match_coverage` | Coverage, confident matches, missing candidates, errors and mean score per list |
| `score_bands` | How many patches fall in each decision band: confident, needs review, no candidate, below threshold |
| `match_errors` | Candidate-search errors grouped, to diagnose systematic problems |
| `commit_reuse` | Commits linked to several emails: series, resends or false positives worth reviewing |
| `matched_pairs` | Email/commit pairs with both dates, for integration-latency analysis |
| `temporal` | SVG figure and monthly CSV: patches, match rate and integration latency over time |
| `sql_querier` | Interactive SQL REPL, or a one-off query, over `original` and `enriched` (non-default) |

See the [Analysis Documentation](src/lkml_ground_truth/analysis/README.md) for all options and how to add a new analysis.

---

## Architecture Details

### Execution Steps

The main execution is split into steps, one module each in [`src/lkml_ground_truth/steps/`](src/lkml_ground_truth/steps/): `repo`, `matching` and `enrich`. Every step exposes `main(config, ...)`, and [`steps/main.py`](src/lkml_ground_truth/steps/main.py) orchestrates them like the analysis orchestrator does: no selection runs all steps in order, and a name (`--step`, or `STEP=` in Make) runs just that one. Because the steps feed each other, a failure stops the run.

The same steps are available from the CLI:

```bash
uv run lkml-ground-truth --config config.toml run                  # all steps
uv run lkml-ground-truth --config config.toml run --step matching  # one step
uv run lkml-ground-truth --config config.toml clone-repo --force   # repo step, forcing the clone
```

### Matching Implementation

The matching step is implemented in Python and works in four phases:

1. **Load**: reads the `list=<name>` Parquet partitions and keeps the emails that contain a diff (`code` column).
2. **Index**: builds (or loads from cache) a `file → [(timestamp, commit)]` index from a single `git log --name-only` pass.
3. **Candidates**: for each patch, selects commits that touch the same files within `[email date − days_before, email date + days_after]`.
4. **Score**: compares the patch with each candidate through PaStA's comparison engine and keeps the best one:

```
score = message_diff_weight × message_similarity + (1 − message_diff_weight) × diff_similarity
```

**Design Principles:**

- **Multi-process**: A `multiprocessing.Pool` scores patches in parallel; the repository and index are loaded once and shared with workers through copy-on-write
- **Resumable**: Results are checkpointed every `checkpoint_every` rows and resumed automatically
- **Deterministic**: Ties between candidates are broken by commit hash
- **Fault-tolerant input**: Parquet reading falls back to PyArrow row-group reads when Polars fails on nested columns

### Enrichment Implementation

The `enrich` step reads the match CSVs and writes them as Parquet under `paths.enriched_root`, one `list=<name>/` partition per mailing list, keyed by `message_id`.

### Analysis Implementation

- **One module per analysis**: each exposes `build()` (a Polars LazyFrame, easy to test) and `main()`; `analysis/main.py` orchestrates them
- **Polars Lazy**: analyses scan the `original` and `enriched` Parquet tables without copying the datasets
- **DataFusion**: the SQL REPL registers only the `list=<name>` partitions you ask for, so one broken list never breaks queries on the others

### Vendored PaStA

[`src/lkml_ground_truth/pasta/`](src/lkml_ground_truth/pasta/) is a minimal copy of the [PaStA](https://github.com/lfd/PaStA) patch comparison engine. It retains its upstream copyright and GPLv2 notices and is excluded from linting to preserve the original style.

---

## Repository Layout

| Path | Purpose |
|------|---------|
| `src/lkml_ground_truth/` | Installable package and CLI (`lkml-ground-truth`) |
| `src/lkml_ground_truth/steps/` | The `repo`, `matching` and `enrich` steps and their orchestrator |
| `src/lkml_ground_truth/analysis/` | One module per analysis, the orchestrator and the DataFusion SQL REPL |
| `src/lkml_ground_truth/pasta/` | Minimal vendored PaStA engine |
| `scripts/` | Stand-alone export, integration and review utilities |
| `tests/` | Automated tests |
| `example_config.toml` | Configuration template |
| `output/` | Generated artifacts; ignored by Git |

---

## Additional Resources

- [Analysis Detailed Documentation](src/lkml_ground_truth/analysis/README.md)
- [Scripts Detailed Documentation](scripts/README.md)
- [Example Configuration](example_config.toml)
- [MailingListsHeritage](https://gitlab.com/ccsl-usp/codev/MailingListsHeritage) - produces the input dataset
- [PaStA](https://github.com/lfd/PaStA) - patch comparison engine

## License

See the [LICENSE](LICENSE) file. The vendored `pasta/` subpackage retains its upstream PaStA copyright and GPLv2 notices.
