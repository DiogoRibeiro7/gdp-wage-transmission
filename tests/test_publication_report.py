from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from tools.publication_report import (
    audit_paper_sources,
    build_paper_packet,
    preflight_pdf,
    verify_dossier,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_dossier(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "driver": "productivity_per_worker",
                "role": "primary",
                "start_year": 1995,
                "end_year": 2025,
                "n_levels": 31,
                "annualized_wage_growth": 0.01,
                "annualized_driver_growth": 0.012,
                "growth_correlation": 0.2,
                "distributed_lag_cumulative": 0.6,
                "distributed_lag_std_error": 0.1,
                "distributed_lag_ci_low": 0.404,
                "distributed_lag_ci_high": 0.796,
                "distributed_lag_p_value": 0.01,
            },
            {
                "driver": "productivity",
                "role": "secondary",
                "start_year": 1995,
                "end_year": 2025,
                "n_levels": 31,
                "annualized_wage_growth": 0.01,
                "annualized_driver_growth": 0.011,
                "growth_correlation": 0.1,
                "distributed_lag_cumulative": 0.4,
                "distributed_lag_std_error": 0.15,
                "distributed_lag_ci_low": 0.106,
                "distributed_lag_ci_high": 0.694,
                "distributed_lag_p_value": 0.04,
            },
        ]
    ).to_csv(root / "core_estimates.csv", index=False)
    pd.DataFrame(
        [
            {
                "driver": "productivity_per_worker",
                "model": "ecm_long_run",
                "claim_eligible": False,
                "policy": "reliability_gated",
                "reason": "unsupported_without_cointegration",
            },
            {
                "driver": "productivity_per_worker",
                "model": "state_space_latest",
                "claim_eligible": True,
                "policy": "reliability_gated",
                "reason": "supported_for_interpretation",
            },
            {
                "driver": "productivity",
                "model": "ecm_long_run",
                "claim_eligible": True,
                "policy": "reliability_gated",
                "reason": "supported",
            },
        ]
    ).to_csv(root / "reliability_gates.csv", index=False)
    pd.DataFrame(
        [
            {
                "driver": "productivity_per_worker",
                "n_countries": 12,
                "median_cumulative_transmission": 0.55,
                "random_effect_estimate": 0.5,
                "random_effect_std_error": 0.08,
                "i_squared_percent": 62.0,
            },
            {
                "driver": "productivity",
                "n_countries": 12,
                "median_cumulative_transmission": 0.45,
                "random_effect_estimate": 0.42,
                "random_effect_std_error": 0.09,
                "i_squared_percent": 55.0,
            },
        ]
    ).to_csv(root / "cross_country_summary.csv", index=False)
    (root / "results_summary.md").write_text("# machine-generated dossier\n", encoding="utf-8")

    outputs = {
        str(root / name): _sha(root / name)
        for name in (
            "core_estimates.csv",
            "reliability_gates.csv",
            "cross_country_summary.csv",
            "results_summary.md",
        )
    }
    manifest = {
        "package_version": "0.6.0",
        "specification_lock_label": "pre-source-freeze-2026-08-22",
        "primary_country": "PRT",
        "primary_driver": "productivity_per_worker",
        "primary_estimand": "distributed_lag_cumulative",
        "inputs": {},
        "outputs": outputs,
        "causal_claims_authorized": False,
    }
    (root / "publication_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return root


def _write_main(paper_dir: Path) -> None:
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "main.tex").write_text(
        "\\input{generated/results_primary.tex}\n"
        "\\input{generated/table_core_estimates.tex}\n"
        "\\input{generated/table_reliability.tex}\n"
        "\\input{generated/table_cross_country.tex}\n",
        encoding="utf-8",
    )


def test_paper_packet_is_generated_only_from_verified_dossier(tmp_path: Path) -> None:
    dossier = _write_dossier(tmp_path / "dossier")
    paper = tmp_path / "paper"
    _write_main(paper)

    packet = build_paper_packet(dossier_dir=dossier, paper_dir=paper)
    audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)

    text = packet.results_primary.read_text(encoding="utf-8")
    assert "\\hat{\\Theta}=0.600" in text
    assert "not interpreted causally" in text
    reliability = packet.reliability_table.read_text(encoding="utf-8")
    assert "not eligible" in reliability
    manifest = json.loads(packet.manifest.read_text(encoding="utf-8"))
    assert manifest["causal_claims_authorized"] is False
    assert all(not Path(key).is_absolute() for key in manifest["outputs"])


def test_dossier_tampering_is_rejected(tmp_path: Path) -> None:
    dossier = _write_dossier(tmp_path / "dossier")
    (dossier / "core_estimates.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_dossier(dossier)


def test_generated_fragment_tampering_is_rejected(tmp_path: Path) -> None:
    dossier = _write_dossier(tmp_path / "dossier")
    paper = tmp_path / "paper"
    _write_main(paper)
    packet = build_paper_packet(dossier_dir=dossier, paper_dir=paper)
    packet.core_table.write_text("manual edit\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)


def test_dossier_input_tampering_is_rejected_after_the_packet_is_built(tmp_path: Path) -> None:
    """A dossier file that moves after the build must fail the audit.

    Tampering with an input leaves every generated fragment matching its recorded digest, so the
    fragment check cannot see it. Only the recorded input digests can.
    """
    dossier = _write_dossier(tmp_path / "dossier")
    paper = tmp_path / "paper"
    _write_main(paper)
    packet = build_paper_packet(dossier_dir=dossier, paper_dir=paper)
    audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)

    (dossier / "results_summary.md").write_text("# edited after the build\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Dossier input has changed"):
        audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)


def test_missing_dossier_input_is_rejected(tmp_path: Path) -> None:
    """A recorded input that disappears is a failure, not a silently skipped check."""
    dossier = _write_dossier(tmp_path / "dossier")
    paper = tmp_path / "paper"
    _write_main(paper)
    packet = build_paper_packet(dossier_dir=dossier, paper_dir=paper)
    (dossier / "results_summary.md").unlink()
    with pytest.raises(FileNotFoundError, match="recorded in the packet is missing"):
        audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)


def test_manual_table_in_paper_source_is_rejected(tmp_path: Path) -> None:
    dossier = _write_dossier(tmp_path / "dossier")
    paper = tmp_path / "paper"
    _write_main(paper)
    packet = build_paper_packet(dossier_dir=dossier, paper_dir=paper)
    (paper / "appendix.tex").write_text(
        "\\begin{table} manually assembled \\end{table}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Manual empirical table"):
        audit_paper_sources(paper_dir=paper, generated_manifest=packet.manifest)


def _stub_paper(root: Path, *, body: bytes) -> Path:
    """A minimal paper directory: a log with no warnings and one source file."""
    paper = root / "paper"
    (paper / "generated").mkdir(parents=True)
    (paper / "main.log").write_text(
        "This is pdfTeX\nOutput written on main.pdf\n", encoding="utf-8"
    )
    (paper / "main.tex").write_bytes(body)
    return paper


def test_preflight_passes_on_a_clean_source(tmp_path: Path) -> None:
    paper = _stub_paper(tmp_path, body=b"Table~" + bytes([92]) + b"ref{tab:x} is fine.\n")

    assert preflight_pdf(paper) == 0


def test_preflight_catches_a_carriage_return_from_a_lost_backslash(tmp_path: Path) -> None:
    """A lost backslash before "ref" leaves 0x0D, which text-mode reads would silently normalise."""
    paper = _stub_paper(tmp_path, body=b"Table~" + bytes([13]) + b"ef{tab:x}\n")

    assert preflight_pdf(paper) == 1


def test_preflight_catches_a_bell_from_a_lost_backslash(tmp_path: Path) -> None:
    paper = _stub_paper(tmp_path, body=bytes([7]) + b"ppendix\n")

    assert preflight_pdf(paper) == 1


def test_preflight_accepts_crlf_line_endings(tmp_path: Path) -> None:
    """A carriage return in a CRLF pair is a line ending, not a mangled command."""
    paper = _stub_paper(tmp_path, body=b"One line.\nAnother line.\n")

    assert preflight_pdf(paper) == 0


def test_preflight_catches_an_undefined_reference(tmp_path: Path) -> None:
    paper = _stub_paper(tmp_path, body=b"Nothing wrong here.\n")
    (paper / "main.log").write_text(
        "LaTeX Warning: Reference `tab:missing' on page 1 undefined on input line 4.\n",
        encoding="utf-8",
    )

    assert preflight_pdf(paper) == 1


def test_preflight_catches_an_overfull_box(tmp_path: Path) -> None:
    paper = _stub_paper(tmp_path, body=b"Nothing wrong here.\n")
    (paper / "main.log").write_text(
        "Overfull \hbox (42.0pt too wide) in paragraph at lines 1--2\n", encoding="utf-8"
    )

    assert preflight_pdf(paper) == 1


def test_preflight_catches_the_appendix_reference_that_reached_the_page(tmp_path: Path) -> None:
    """The exact defect that printed "efsec:panel-appendix" in a compiled manuscript.

    A backslash lost from ``\ref`` inside a generation script leaves 0x0D followed by "ef",
    which TeX typesets as literal text and warns about nothing. Two independent checks should
    see it: the stray control byte, and the damaged-command pattern.
    """
    paper = _stub_paper(
        tmp_path, body=b"see Appendix~" + bytes([13]) + b"ef{sec:panel-appendix} for detail.\n"
    )

    assert preflight_pdf(paper) == 1


def test_preflight_reads_generated_fragments_as_bytes_too(tmp_path: Path) -> None:
    """Generated fragments are where mangled commands are actually produced."""
    paper = _stub_paper(tmp_path, body=b"Nothing wrong in the manuscript.\n")
    (paper / "generated" / "table_dynamic_panel.tex").write_bytes(
        b"Table~" + bytes([13]) + b"ef{tab:dynamic-panel}\n"
    )

    assert preflight_pdf(paper) == 1


def test_preflight_does_not_flag_an_intact_reference_to_a_section(tmp_path: Path) -> None:
    """`ef{sec:` is a substring of `\ref{sec:`; the check must not fire on the intact command."""
    paper = _stub_paper(
        tmp_path, body=b"see Appendix~" + bytes([92]) + b"ref{sec:dynamic-panel} for detail.\n"
    )

    assert preflight_pdf(paper) == 0
