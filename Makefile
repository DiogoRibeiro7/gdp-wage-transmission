.PHONY: install test lint typecheck check demo spec-lock freeze-plan freeze-fetch freeze-audit snapshot-registry publication-gate publication-dossier paper-packet paper-audit paper2-breaks paper2-pdf

install:
	poetry install

test:
	poetry run pytest

lint:
	poetry run ruff check .

typecheck:
	poetry run mypy src

check: lint typecheck test

demo:
	poetry run wage-transmission analyse --input data/sample/synthetic_portugal.csv --country PRT --output results/demo

spec-lock:
	poetry run wage-transmission lock-publication-spec \
		--label pre-source-freeze-2026-08-22 \
		--output paper/specification_lock.json

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
		--specification-lock paper/specification_lock.json \
		--output results/vintages/$(VINTAGE)/publication_dossier


paper-packet:
	@test -n "$(VINTAGE)" || (echo "Usage: make paper-packet VINTAGE=YYYY-MM-DD" && exit 2)
	poetry run python tools/publication_report.py build \
		--dossier results/vintages/$(VINTAGE)/publication_dossier \
		--paper-dir paper


paper-audit:
	poetry run python tools/publication_report.py audit \
		--paper-dir paper \
		--manifest paper/generated/paper_packet_manifest.json


paper2-breaks:
	PYTHONPATH=.:src poetry run python tools/wage_distribution_breaks.py \
		--input results/exploratory_live/wage_distribution/portugal_wage_distribution_2002_2024.csv \
		--output-dir results/exploratory_live/wage_distribution_breaks \
		--paper-dir papers/wage_distribution_breaks


paper2-pdf: paper2-breaks
	cd papers/wage_distribution_breaks && pdflatex -interaction=nonstopmode -halt-on-error main.tex
