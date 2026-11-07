include containers.mk

CONFIG ?= config.toml
IMAGE  := rebuild-lost-link
CLI    := rebuild-lost-link --config $(CONFIG)

# Run natively when uv is installed, otherwise inside the container image
# (docker or podman, see containers.mk).
ifeq ($(shell command -v uv 2>/dev/null),)
RUN = $(CONTAINER) run --rm -it --user $(shell id -u):$(shell id -g) -v $(CURDIR):/app $(IMAGE) --config $(CONFIG)
else
RUN = uv run $(CLI)
endif

.PHONY: config run repo enrich analyze test lint fmt image clean

config:  ## copy example_config.toml to config.toml
	@test -f $(CONFIG) || cp example_config.toml $(CONFIG)

run:     ## repo -> match -> enrich
	$(RUN) run

repo:    ## clone the kernel repository (see repo.since in the config)
	$(RUN) repo

enrich:
	$(RUN) enrich

analyze: ## NAMES="coverage patch_size_outcomes" LISTS=iio,bpf
	$(RUN) analyze $(NAMES) --list "$(or $(LISTS),all)"

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

image:
	$(CONTAINER) build -t $(IMAGE) .

clean:
	rm -rf .venv .nox .ruff_cache .pytest_cache htmlcov .coverage
