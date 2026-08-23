"""Command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer
import yaml

from wage_transmission.config import load_models_config, load_publication_config
from wage_transmission.cross_country import (
    estimate_country_robustness,
    summarise_country_robustness,
    write_country_robustness,
)
from wage_transmission.data.common import sha256_bytes
from wage_transmission.data.eurostat import download_decomposition_inputs, download_real_gdp
from wage_transmission.data.fetch import FetchPolicy, fetch_source_freeze
from wage_transmission.data.oecd import (
    canonicalise_average_wages,
    canonicalise_gdp_per_employed,
    canonicalise_productivity,
    download_average_wages,
    download_gdp_per_employed,
    download_productivity,
)
from wage_transmission.data.offline import (
    build_decomposition_from_snapshots,
    build_oecd_panel_from_snapshots,
)
from wage_transmission.data.panel import add_driver, add_real_gdp, merge_wages_productivity
from wage_transmission.data.revisions import compare_vintages
from wage_transmission.data.snapshots import (
    import_external_snapshot,
    verify_snapshot,
    write_snapshot_registry,
)
from wage_transmission.data.source_queries import (
    audit_source_freeze,
    build_source_queries,
    source_queries_from_manifest,
)
from wage_transmission.decomposition import decompose_panel
from wage_transmission.pipeline import analyse_country
from wage_transmission.plots import plot_cumulative_decomposition, plot_decomposition_components
from wage_transmission.publication import (
    build_publication_dossier,
    build_specification_lock,
    write_specification_lock,
)
from wage_transmission.reporting import write_json
from wage_transmission.version import __version__

app = typer.Typer(no_args_is_help=True, help="GDP–wage transmission research pipeline.")


def _resolve_raw_dir(raw_dir: Path, vintage: str | None) -> Path:
    """Resolve an optional explicit source-vintage subdirectory safely."""
    if vintage is None:
        return raw_dir
    clean = vintage.strip()
    if not clean or Path(clean).name != clean or clean in {".", ".."}:
        raise typer.BadParameter("--vintage must be one directory name, e.g. 2026-08-22.")
    return raw_dir / clean


@app.command("analyse")
def analyse(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    country: str = typer.Option("PRT", "--country"),
    output: Path = typer.Option(Path("results/portugal"), "--output"),
    driver: str = typer.Option("productivity", "--driver"),
    models_config: Path = typer.Option(Path("config/models.yml"), "--models-config"),
) -> None:
    """Run the core models on one canonical country panel."""
    frame = pd.read_csv(input_path)
    if "country" in frame.columns:
        frame = frame.loc[frame["country"].astype(str) == country].copy()
    model_config = load_models_config(models_config)
    analyse_country(frame, output, driver_column=driver, model_config=model_config)
    write_json(
        {
            "package_version": __version__,
            "country": country,
            "driver": driver,
            "input_path": str(input_path),
            "input_sha256": sha256_bytes(input_path.read_bytes()),
            "models_config_path": str(models_config),
            "models_config_sha256": sha256_bytes(models_config.read_bytes()),
        },
        output / "run_manifest.json",
    )
    typer.echo(f"Analysis written to {output}")


@app.command("analyse-panel")
def analyse_panel(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    output: Path = typer.Option(Path("results/cross_country/country_estimates.csv"), "--output"),
    driver: str = typer.Option("productivity", "--driver"),
    models_config: Path = typer.Option(Path("config/models.yml"), "--models-config"),
    min_observations: int = typer.Option(20, "--min-observations", min=12),
) -> None:
    """Estimate the core transmission quantities separately for every country."""
    panel = pd.read_csv(input_path)
    config = load_models_config(models_config)
    estimates = estimate_country_robustness(
        panel,
        driver_column=driver,
        config=config,
        min_observations=min_observations,
    )
    write_country_robustness(estimates, output)
    if len(estimates) >= 2:
        summary = summarise_country_robustness(estimates, driver=driver)
        summary_path = output.with_suffix(".summary.json")
        write_json(summary, summary_path)
        typer.echo(
            f"Country robustness estimates written to {output} ({len(estimates)} countries); "
            f"summary written to {summary_path}"
        )
    else:
        typer.echo(f"Country robustness estimates written to {output} ({len(estimates)} countries)")


@app.command("download-oecd")
def download_oecd(
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    start_year: int | None = typer.Option(None, "--start-year"),
    end_year: int | None = typer.Option(None, "--end-year"),
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    vintage: str | None = typer.Option(None, "--vintage"),
    output: Path = typer.Option(Path("data/processed/panel.csv"), "--output"),
) -> None:
    """Download OECD wage/productivity data and build a canonical panel."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    countries = [str(value) for value in config["countries"]]
    start = int(config["start_year"] if start_year is None else start_year)
    end = int(config["end_year"] if end_year is None else end_year)
    resolved_raw_dir = _resolve_raw_dir(raw_dir, vintage)

    wage_download = download_average_wages(
        countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir
    )
    productivity_download = download_productivity(
        countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir
    )
    wages = canonicalise_average_wages(wage_download.frame)
    productivity = canonicalise_productivity(productivity_download.frame)
    panel = merge_wages_productivity(wages, productivity)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    typer.echo(f"Canonical panel written to {output} ({len(panel)} rows)")


@app.command("download-oecd-matched")
def download_oecd_matched(
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    start_year: int | None = typer.Option(None, "--start-year"),
    end_year: int | None = typer.Option(None, "--end-year"),
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    vintage: str | None = typer.Option(None, "--vintage"),
    output: Path = typer.Option(Path("data/processed/panel_per_worker.csv"), "--output"),
) -> None:
    """Download annual wages with GDP per person employed as the matched annual driver."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    countries = [str(value) for value in config["countries"]]
    start = int(config["start_year"] if start_year is None else start_year)
    end = int(config["end_year"] if end_year is None else end_year)
    resolved_raw_dir = _resolve_raw_dir(raw_dir, vintage)

    wage_download = download_average_wages(
        countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir
    )
    worker_download = download_gdp_per_employed(
        countries,
        start_year=start,
        end_year=end,
        raw_dir=resolved_raw_dir,
    )
    wages = canonicalise_average_wages(wage_download.frame)
    per_worker = canonicalise_gdp_per_employed(worker_download.frame)
    # Build from the wage years and retain the denominator-explicit driver column.
    base = wages.loc[:, ["country", "year", "real_wage"]].copy()
    panel = add_driver(base, per_worker, column="productivity_per_worker")
    panel = panel.dropna(subset=["productivity_per_worker"]).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    typer.echo(f"Matched annual panel written to {output} ({len(panel)} rows)")


@app.command("download-decomposition")
def download_decomposition(
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    start_year: int | None = typer.Option(None, "--start-year"),
    end_year: int | None = typer.Option(None, "--end-year"),
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    vintage: str | None = typer.Option(None, "--vintage"),
    output: Path = typer.Option(Path("data/processed/decomposition_inputs.csv"), "--output"),
    coverage_output: Path = typer.Option(
        Path("data/processed/decomposition_coverage.csv"), "--coverage-output"
    ),
) -> None:
    """Download the Eurostat national-accounts inputs for the exact wage decomposition."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    country_values = config.get("decomposition_countries", config["countries"])
    countries = [str(value) for value in country_values]
    start = int(config["start_year"] if start_year is None else start_year)
    end = int(config["end_year"] if end_year is None else end_year)
    resolved_raw_dir = _resolve_raw_dir(raw_dir, vintage)
    panel = download_decomposition_inputs(
        countries,
        start_year=start,
        end_year=end,
        raw_dir=resolved_raw_dir,
        coverage_path=coverage_output,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    typer.echo(
        f"Decomposition input panel written to {output} ({len(panel)} rows); "
        f"coverage audit written to {coverage_output}"
    )


@app.command("decompose")
def decompose(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("results/decomposition"), "--output"),
    country: str | None = typer.Option(None, "--country"),
) -> None:
    """Run the exact national-accounts decomposition for one country or a panel."""
    frame = pd.read_csv(input_path)
    if country is not None:
        if "country" not in frame.columns:
            raise typer.BadParameter("--country requires a `country` column in the input panel.")
        frame = frame.loc[frame["country"].astype(str) == country].copy()
        if frame.empty:
            raise typer.BadParameter(f"No rows found for country {country!r}.")

    components, summaries = decompose_panel(frame)
    output_dir.mkdir(parents=True, exist_ok=True)
    components_path = output_dir / "decomposition_components.csv"
    components.to_csv(components_path, index=False)
    write_json(summaries, output_dir / "decomposition_summary.json")
    if len(summaries) == 1:
        plot_frame = components
        plot_decomposition_components(plot_frame, output_dir / "decomposition_annual.png")
        plot_cumulative_decomposition(plot_frame, output_dir / "decomposition_cumulative.png")
    write_json(
        {
            "package_version": __version__,
            "country_filter": country,
            "input_path": str(input_path),
            "input_sha256": sha256_bytes(input_path.read_bytes()),
            "identity": "dlog(real compensation per employee) = dlog(real GDP) + "
            "dlog(labour share) - dlog(employees) + (GDP-deflator inflation - HICP inflation)",
        },
        output_dir / "run_manifest.json",
    )
    typer.echo(
        f"Decomposition written to {components_path}; {len(summaries)} country summaries created"
    )


@app.command("download-data")
def download_data(
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    vintage: str | None = typer.Option(None, "--vintage"),
    output: Path = typer.Option(Path("data/processed/panel.csv"), "--output"),
) -> None:
    """Download OECD wages/productivity plus Eurostat real GDP where available."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    countries = [str(value) for value in config["countries"]]
    start = int(config["start_year"])
    end = int(config["end_year"])
    resolved_raw_dir = _resolve_raw_dir(raw_dir, vintage)

    wage_download = download_average_wages(
        countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir
    )
    productivity_download = download_productivity(
        countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir
    )
    wages = canonicalise_average_wages(wage_download.frame)
    productivity = canonicalise_productivity(productivity_download.frame)
    panel = merge_wages_productivity(wages, productivity)

    gdp = download_real_gdp(countries, start_year=start, end_year=end, raw_dir=resolved_raw_dir)
    if not gdp.empty:
        panel = add_real_gdp(panel, gdp)

    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    typer.echo(f"Canonical panel written to {output} ({len(panel)} rows)")


@app.command("export-source-queries")
def export_source_queries(
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    vintage: str | None = typer.Option(None, "--vintage"),
    output: Path = typer.Option(Path("data/source_queries.json"), "--output"),
) -> None:
    """Export exact OECD/Eurostat request URLs without performing network I/O."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    countries = [str(value) for value in config["countries"]]
    decomposition_countries = [
        str(value) for value in config.get("decomposition_countries", countries)
    ]
    start = int(config["start_year"])
    end = int(config["end_year"])
    resolved_raw = raw_dir / vintage if vintage is not None else raw_dir
    queries = build_source_queries(
        countries=countries,
        decomposition_countries=decomposition_countries,
        start_year=start,
        end_year=end,
        raw_root=resolved_raw,
    )
    write_json(
        {
            "package_version": __version__,
            "project_config": str(project_config),
            "project_config_sha256": sha256_bytes(project_config.read_bytes()),
            "vintage": vintage,
            "queries": [query.to_dict() for query in queries],
        },
        output,
    )
    typer.echo(f"Source-query manifest written to {output} ({len(queries)} queries)")


@app.command("fetch-source-freeze")
def fetch_source_freeze_command(
    query_manifest: Path = typer.Option(..., "--query-manifest", exists=True, readable=True),
    output: Path = typer.Option(Path("data/source_fetch.csv"), "--output"),
    audit_output: Path = typer.Option(Path("data/source_freeze_audit.csv"), "--audit-output"),
    registry: Path = typer.Option(Path("data/raw/SNAPSHOT_REGISTRY.csv"), "--registry"),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
    retries: int = typer.Option(3, "--retries", min=0, max=10),
    timeout_seconds: float = typer.Option(60.0, "--timeout", min=1.0),
    backoff_seconds: float = typer.Option(1.0, "--backoff", min=0.0),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    """Fetch every exact URL in a source manifest and freeze the response bytes unchanged."""
    payload = json.loads(query_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("--query-manifest must contain a JSON object.")
    queries = source_queries_from_manifest(payload)
    policy = FetchPolicy(
        timeout_seconds=timeout_seconds,
        retries=retries,
        backoff_seconds=backoff_seconds,
    )
    results = fetch_source_freeze(
        queries,
        policy=policy,
        manifest_path=query_manifest,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output, index=False)
    write_snapshot_registry(raw_root, registry)

    audit = audit_source_freeze(queries)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_output, index=False)
    failed = results.loc[results["status"] == "failed", "query_id"].astype(str).tolist()
    incomplete = audit.loc[audit["status"] != "verified", "query_id"].astype(str).tolist()
    downloaded = int((results["status"] == "downloaded").sum())
    reused = int((results["status"] == "reused_verified").sum())
    typer.echo(
        f"Source freeze fetch complete: {downloaded} downloaded, {reused} reused, "
        f"{len(failed)} failed; audit written to {audit_output}"
    )
    if strict and incomplete:
        preview = ", ".join(incomplete[:10])
        suffix = " ..." if len(incomplete) > 10 else ""
        typer.echo(
            f"Publication gate failed: {len(incomplete)} incomplete queries: {preview}{suffix}",
            err=True,
        )
        raise typer.Exit(code=2) from None


@app.command("import-query-snapshot")
def import_query_snapshot(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    query_manifest: Path = typer.Option(..., "--query-manifest", exists=True, readable=True),
    query_id: str = typer.Option(..., "--query-id"),
    registry: Path = typer.Option(Path("data/raw/SNAPSHOT_REGISTRY.csv"), "--registry"),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
) -> None:
    """Import one externally downloaded payload using metadata from an exported query manifest."""
    payload = json.loads(query_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("--query-manifest must contain a JSON object.")
    queries = source_queries_from_manifest(payload)
    matches = [query for query in queries if query.query_id == query_id]
    if len(matches) != 1:
        raise typer.BadParameter(f"Query id {query_id!r} was not found exactly once.")
    query = matches[0]
    metadata = {
        "source": query.source,
        "url": query.url,
        "dataset": query.dataset,
        "flow": query.flow,
        "measure": query.measure,
        "query_id": query.query_id,
        "purpose": query.purpose,
        "query_manifest": str(query_manifest),
        "query_manifest_sha256": sha256_bytes(query_manifest.read_bytes()),
    }
    raw_path, metadata_path = import_external_snapshot(
        input_path,
        Path(query.expected_raw_path),
        metadata=metadata,
    )
    verified = verify_snapshot(raw_path, metadata_path)
    write_snapshot_registry(raw_root, registry)
    typer.echo(
        f"Imported {query.query_id} -> {raw_path} "
        f"({verified.bytes} bytes, sha256={verified.sha256})"
    )


@app.command("audit-source-freeze")
def audit_source_freeze_command(
    query_manifest: Path = typer.Option(..., "--query-manifest", exists=True, readable=True),
    output: Path = typer.Option(Path("data/source_freeze_audit.csv"), "--output"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    """Check whether every payload in a query manifest is present and hash-verified."""
    payload = json.loads(query_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("--query-manifest must contain a JSON object.")
    queries = source_queries_from_manifest(payload)
    audit = audit_source_freeze(queries)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output, index=False)
    counts = audit["status"].value_counts().to_dict()
    typer.echo(f"Source freeze audit written to {output}: {counts}")
    incomplete = audit.loc[audit["status"] != "verified", "query_id"].astype(str).tolist()
    if strict and incomplete:
        preview = ", ".join(incomplete[:10])
        suffix = " ..." if len(incomplete) > 10 else ""
        typer.echo(
            f"Publication gate failed: {len(incomplete)} incomplete queries: {preview}{suffix}",
            err=True,
        )
        raise typer.Exit(code=2) from None


@app.command("import-snapshot")
def import_snapshot(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    destination: Path = typer.Option(..., "--destination"),
    metadata_path: Path = typer.Option(..., "--metadata", exists=True, readable=True),
    registry: Path | None = typer.Option(None, "--registry"),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
) -> None:
    """Import an externally downloaded official payload without changing its bytes."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise typer.BadParameter("--metadata must contain one JSON object.")
    raw_path, adjacent_metadata = import_external_snapshot(
        input_path,
        destination,
        metadata=metadata,
    )
    verified = verify_snapshot(raw_path, adjacent_metadata)
    if registry is not None:
        write_snapshot_registry(raw_root, registry)
    typer.echo(
        f"Imported immutable snapshot {raw_path} ({verified.bytes} bytes, sha256={verified.sha256})"
    )


@app.command("audit-snapshots")
def audit_snapshots(
    raw_dir: Path = typer.Option(Path("data/raw"), "--raw-dir"),
    output: Path = typer.Option(Path("data/raw/SNAPSHOT_REGISTRY.csv"), "--output"),
) -> None:
    """Verify all frozen source payloads and rebuild the raw snapshot registry."""
    write_snapshot_registry(raw_dir, output)
    registry = pd.read_csv(output)
    typer.echo(f"Verified {len(registry)} raw snapshots; registry written to {output}")


@app.command("build-oecd-from-snapshots")
def build_oecd_from_snapshots(
    wage_snapshot: Path = typer.Option(..., "--wage-snapshot", exists=True, readable=True),
    productivity_snapshot: Path = typer.Option(
        ..., "--productivity-snapshot", exists=True, readable=True
    ),
    measure: str = typer.Option("GDPEMP", "--measure"),
    output: Path = typer.Option(Path("data/processed/panel_per_worker.csv"), "--output"),
    allow_unverified: bool = typer.Option(False, "--allow-unverified"),
) -> None:
    """Build the OECD analytical panel from locally frozen source bytes only."""
    normalized = measure.upper()
    if normalized not in {"GDPHRS", "GDPEMP"}:
        raise typer.BadParameter("--measure must be GDPHRS or GDPEMP.")
    panel = build_oecd_panel_from_snapshots(
        wage_snapshot,
        productivity_snapshot,
        measure=normalized,  # type: ignore[arg-type]
        require_metadata=not allow_unverified,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    write_json(
        {
            "package_version": __version__,
            "measure": normalized,
            "wage_snapshot": str(wage_snapshot),
            "wage_sha256": sha256_bytes(wage_snapshot.read_bytes()),
            "productivity_snapshot": str(productivity_snapshot),
            "productivity_sha256": sha256_bytes(productivity_snapshot.read_bytes()),
            "require_metadata": not allow_unverified,
        },
        output.with_suffix(".manifest.json"),
    )
    typer.echo(f"Offline OECD panel written to {output} ({len(panel)} rows)")


@app.command("build-decomposition-from-snapshots")
def build_decomposition_from_frozen(
    raw_dir: Path = typer.Option(..., "--raw-dir", exists=True, file_okay=False),
    project_config: Path = typer.Option(Path("config/project.yml"), "--project-config"),
    output: Path = typer.Option(Path("data/processed/decomposition_inputs.csv"), "--output"),
    coverage_output: Path = typer.Option(
        Path("data/processed/decomposition_coverage.csv"), "--coverage-output"
    ),
    allow_unverified: bool = typer.Option(False, "--allow-unverified"),
) -> None:
    """Build decomposition inputs from frozen Eurostat JSON-stat payloads without HTTP."""
    config = yaml.safe_load(project_config.read_text(encoding="utf-8"))
    countries = [str(value) for value in config.get("decomposition_countries", config["countries"])]
    start = int(config["start_year"])
    end = int(config["end_year"])
    panel = build_decomposition_from_snapshots(
        raw_dir,
        countries=countries,
        start_year=start,
        end_year=end,
        coverage_path=coverage_output,
        require_metadata=not allow_unverified,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    write_json(
        {
            "package_version": __version__,
            "raw_dir": str(raw_dir),
            "project_config_sha256": sha256_bytes(project_config.read_bytes()),
            "require_metadata": not allow_unverified,
        },
        output.with_suffix(".manifest.json"),
    )
    typer.echo(
        f"Offline decomposition panel written to {output} ({len(panel)} rows); "
        f"coverage audit written to {coverage_output}"
    )


@app.command("compare-vintages")
def compare_data_vintages(
    old_path: Path = typer.Option(..., "--old", exists=True, readable=True),
    new_path: Path = typer.Option(..., "--new", exists=True, readable=True),
    values: str = typer.Option(..., "--values", help="Comma-separated numeric columns."),
    output: Path = typer.Option(Path("results/revisions.csv"), "--output"),
) -> None:
    """Quantify additions, deletions, and numeric revisions between processed vintages."""
    value_columns = [value.strip() for value in values.split(",") if value.strip()]
    old = pd.read_csv(old_path)
    new = pd.read_csv(new_path)
    revisions, summaries = compare_vintages(old, new, value_columns=value_columns)
    output.parent.mkdir(parents=True, exist_ok=True)
    revisions.to_csv(output, index=False)
    write_json(
        {
            "package_version": __version__,
            "old_path": str(old_path),
            "old_sha256": sha256_bytes(old_path.read_bytes()),
            "new_path": str(new_path),
            "new_sha256": sha256_bytes(new_path.read_bytes()),
            "summaries": [summary.to_dict() for summary in summaries],
        },
        output.with_suffix(".summary.json"),
    )
    typer.echo(f"Revision audit written to {output}")


if __name__ == "__main__":
    app()


@app.command("lock-publication-spec")
def lock_publication_spec(
    project_config: Path = typer.Option(
        Path("config/project.yml"), "--project-config", exists=True, readable=True
    ),
    models_config: Path = typer.Option(
        Path("config/models.yml"), "--models-config", exists=True, readable=True
    ),
    publication_config: Path = typer.Option(
        Path("config/publication.yml"), "--publication-config", exists=True, readable=True
    ),
    label: str = typer.Option("pre-source-freeze-2026-08-22", "--label"),
    output: Path = typer.Option(Path("paper/specification_lock.json"), "--output"),
) -> None:
    """Freeze pre-results configuration hashes; never overwrite a different existing lock."""
    lock = build_specification_lock(
        project_config=project_config,
        models_config=models_config,
        publication_config=publication_config,
        label=label,
    )
    try:
        write_specification_lock(lock, output)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Publication specification lock written to {output}")


@app.command("build-publication-dossier")
def build_publication_dossier_command(
    results_root: Path = typer.Option(
        ..., "--results-root", exists=True, file_okay=False, readable=True
    ),
    specification_lock: Path = typer.Option(
        Path("paper/specification_lock.json"),
        "--specification-lock",
        exists=True,
        readable=True,
    ),
    publication_config: Path = typer.Option(
        Path("config/publication.yml"),
        "--publication-config",
        exists=True,
        readable=True,
    ),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Build the pre-specified paper-facing result dossier from one verified result vintage."""
    config = load_publication_config(publication_config)
    output_dir = results_root / "publication_dossier" if output is None else output
    country_results = {
        "productivity_per_worker": results_root / "portugal_per_worker" / "model_results.json",
        "productivity": results_root / "portugal_per_hour" / "model_results.json",
    }
    cross_country_results = {
        "productivity_per_worker": results_root / "cross_country_per_worker.csv",
        "productivity": results_root / "cross_country_per_hour.csv",
    }
    decomposition_summary = results_root / "portugal_decomposition" / "decomposition_summary.json"
    required_paths = [*country_results.values(), *cross_country_results.values()]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise typer.BadParameter("Missing required empirical outputs: " + ", ".join(missing))
    decomposition = decomposition_summary if decomposition_summary.is_file() else None
    dossier = build_publication_dossier(
        country_results=country_results,
        cross_country_results=cross_country_results,
        decomposition_summary=decomposition,
        specification_lock=specification_lock,
        publication_config=config,
        output_dir=output_dir,
    )
    typer.echo(
        f"Publication dossier written to {output_dir}; summary={dossier.summary_markdown}, "
        f"manifest={dossier.manifest}"
    )
