REPO_ROOT ?= $(abspath $(CURDIR)/../../..)
CONFIG ?= $(REPO_ROOT)/config.toml
RESULTS_DIR ?= $(REPO_ROOT)/output/analysis
ANALYSIS ?= dataset_coverage
LIST ?= all

RESULT_FILE := $(RESULTS_DIR)/$(ANALYSIS).csv

.PHONY: help
help:
	@echo "Use: make -C src/lkml_ground_truth/analysis run ANALYSIS=<name> [LIST=<list>]"
	@echo "Interactive SQL: make analysis ANALYSIS=sql_querier.py [LIST=<list>] (from the repository root)"
	@echo "Available analyses: commit_reuse, dataset_coverage, match_coverage, match_errors, score_bands, matched_pairs"

.PHONY: run
run:
	@mkdir -p "$(RESULTS_DIR)"
	@cd "$(REPO_ROOT)" && uv run python -m lkml_ground_truth.analysis.run \
		--config "$(CONFIG)" --analysis "$(ANALYSIS)" --list "$(LIST)" \
		--output "$(RESULT_FILE)"
	@echo "==> Result saved to $(RESULT_FILE)"