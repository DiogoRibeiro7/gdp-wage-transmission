.PHONY: help install hooks format format-check lint typecheck test coverage check build clean integrity release-manifest release-manifest-verify release-archive demo freeze-plan freeze-fetch freeze-audit snapshot-registry publication-gate publication-dossier wage-distribution-breaks

# Default target: list the documented entry points.
help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-22s %s%s", $$1, $$2, ORS}'

install: ## Install runtime and development dependencies from poetry.lock
	poetry install

hooks: ## Install the pre-commit hooks into this checkout
	poetry run pre-commit install

format: ## Rewrite the tree with ruff format and apply safe lint fixes
	poetry run ruff format .
	poetry run ruff check --fix .

format-check: ## Fail if the tree is not ruff-formatted
	poetry run ruff format --check .

lint: ## Run the ruff linter
	poetry run ruff check .

typecheck: ## Run mypy in strict mode over the package
	poetry run mypy src

test: ## Run the test suite
	poetry run pytest

coverage: ## Run the test suite with a coverage report
	poetry run pytest --cov=wage_transmission --cov-report=term-missing --cov-report=html

check: lint format-check typecheck test ## Run every quality gate CI runs

build: ## Build the sdist and wheel
	poetry build

clean: ## Remove build, cache and coverage artefacts
	rm -rf dist build htmlcov .coverage coverage.xml
	rm -rf .pytest_cache .mypy_cache .ruff_cache

REF ?= HEAD

integrity: release-manifest-verify release-archive ## Verify every recorded integrity artefact

release-manifest: ## Regenerate RELEASE_MANIFEST.sha256 over its resolved scope
	poetry run python tools/integrity.py release-manifest write

release-manifest-verify: ## Check RELEASE_MANIFEST.sha256 against the working tree
	poetry run python tools/integrity.py release-manifest verify

release-archive: ## Check that git's archive of REF matches the manifest it carries
	poetry run python tools/integrity.py release-archive verify --ref $(REF)

demo: ## Run the pipeline against the bundled synthetic sample
	poetry run wage-transmission analyse --input data/sample/synthetic_portugal.csv --country PRT --output results/demo

freeze-plan:
	@test -n "$(VINTAGE)" || (echo "Usage: make freeze-plan VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run wage-transmission export-source-queries \
		--vintage $(VINTAGE) \
		--output data/query_manifests/$(VINTAGE).json

freeze-fetch:
	@test -n "$(VINTAGE)" || (echo "Usage: make freeze-fetch VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run wage-transmission fetch-source-freeze \
		--query-manifest data/query_manifests/$(VINTAGE).json \
		--output data/query_manifests/$(VINTAGE).fetch.csv \
		--audit-output data/query_manifests/$(VINTAGE).audit.csv \
		--registry data/raw/SNAPSHOT_REGISTRY.csv \
		--strict

freeze-audit:
	@test -n "$(VINTAGE)" || (echo "Usage: make freeze-audit VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run wage-transmission audit-source-freeze \
		--query-manifest data/query_manifests/$(VINTAGE).json \
		--output data/query_manifests/$(VINTAGE).audit.csv

snapshot-registry:
	poetry run wage-transmission audit-snapshots \
		--raw-dir data/raw \
		--output data/raw/SNAPSHOT_REGISTRY.csv

publication-gate:
	@test -n "$(VINTAGE)" || (echo "Usage: make publication-gate VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run wage-transmission audit-source-freeze \
		--query-manifest data/query_manifests/$(VINTAGE).json \
		--output data/query_manifests/$(VINTAGE).audit.csv \
		--strict

publication-dossier:
	@test -n "$(VINTAGE)" || (echo "Usage: make publication-dossier VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run wage-transmission build-publication-dossier \
		--results-root results/vintages/$(VINTAGE) \
		--output results/vintages/$(VINTAGE)/publication_dossier

wage-distribution-breaks:
	PYTHONPATH=.:src poetry run python tools/wage_distribution_breaks.py \
		--input results/exploratory_live/wage_distribution/portugal_wage_distribution_2002_2024.csv \
		--output-dir results/exploratory_live/wage_distribution_breaks
