"""Build and audit paper-facing report fragments from a verified publication dossier.

This module is intentionally outside ``src/wage_transmission``. It may format already
computed results, but it must never estimate models or alter the locked empirical
specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import beta

REQUIRED_DOSSIER_FILES: tuple[str, ...] = (
    "core_estimates.csv",
    "reliability_gates.csv",
    "cross_country_summary.csv",
    "results_summary.md",
    "publication_manifest.json",
)

REQUIRED_GENERATED_FILES: tuple[str, ...] = (
    "results_primary.tex",
    "table_core_estimates.tex",
    "table_reliability.tex",
    "table_cross_country.tex",
    "results_summary.md",
)

MANUAL_TABLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\\begin\s*\{table\*?\}"),
    re.compile(r"\\begin\s*\{tabular\*?\}"),
    re.compile(r"\\begin\s*\{longtable\}"),
)


@dataclass(frozen=True)
class PaperPacket:
    """Paths generated for one publication dossier."""

    generated_dir: Path
    results_primary: Path
    core_table: Path
    reliability_table: Path
    cross_country_table: Path
    decomposition_table: Path | None
    markdown_summary: Path
    manifest: Path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return {str(key): value for key, value in raw.items()}


def verify_dossier(dossier_dir: Path) -> dict[str, Any]:
    """Verify the dossier's manifest and mandatory machine-generated outputs."""
    if not dossier_dir.is_dir():
        raise FileNotFoundError(dossier_dir)
    missing = [name for name in REQUIRED_DOSSIER_FILES if not (dossier_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Publication dossier missing required files: {missing}")

    manifest_path = dossier_dir / "publication_manifest.json"
    manifest = _load_json_object(manifest_path)
    if manifest.get("causal_claims_authorized") is not False:
        raise ValueError("Publication dossier must explicitly disable causal claims.")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("publication_manifest.json must contain an outputs object.")

    expected_by_name: dict[str, str] = {}
    for raw_path, digest in outputs.items():
        if not isinstance(raw_path, str) or not isinstance(digest, str):
            raise ValueError("Publication manifest output entries must be path -> SHA-256 strings.")
        expected_by_name[Path(raw_path).name] = digest

    for name in REQUIRED_DOSSIER_FILES[:-1]:
        path = dossier_dir / name
        expected = expected_by_name.get(name)
        if expected is None:
            raise ValueError(f"Dossier manifest does not bind required output: {name}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"Dossier output hash mismatch: {name}")

    decomposition = dossier_dir / "decomposition_summary.csv"
    if decomposition.is_file():
        expected = expected_by_name.get(decomposition.name)
        if expected is None or sha256_file(decomposition) != expected:
            raise ValueError("Dossier decomposition output is not correctly manifest-bound.")
    return manifest


def _escape_latex(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _fmt_float(value: Any, digits: int = 3) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    if not math.isfinite(numeric):
        return "--"
    return f"{numeric:.{digits}f}"


def _fmt_pct_fraction(value: Any, digits: int = 1) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    if not math.isfinite(numeric):
        return "--"
    return f"{100.0 * numeric:.{digits}f}\\%"


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    # numpy booleans arrive from pandas and are not instances of bool or int.
    item = getattr(value, "item", None)
    if callable(item) and getattr(value, "shape", None) == ():
        value = item()
        if isinstance(value, bool):
            return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", ""}:
            return False
    raise ValueError(f"Cannot interpret boolean value: {value!r}")


def _driver_label(driver: str) -> str:
    labels = {
        "productivity_per_worker": "GDP per person employed",
        "productivity": "GDP per hour",
        "real_gdp": "Real GDP",
    }
    return labels.get(driver, driver.replace("_", " "))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF explicitly. These fragments are hashed into the packet manifest, so their bytes must not
    # depend on the platform; and a CRLF file would hide a stray carriage return left behind by a
    # command mangled during generation, which is exactly what preflight looks for.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n")
    return path


def _table_wrapper(
    *,
    caption: str,
    label: str,
    columns: str,
    header: str,
    rows: Iterable[str],
    size: str = "footnotesize",
) -> str:
    """Render one table. Tables carry a caption and no note.

    Everything a reader needs in order to interpret a table belongs in the running text, where it
    is read. A note under a float is small print, and the material that used to sit there is now
    part of the manuscript prose.
    """
    body = "\n".join(rows)
    return f"""% AUTO-GENERATED. DO NOT EDIT.
\\begin{{table}}[htbp]
\\centering
\\{size}
\\caption{{{caption}}}
\\label{{{label}}}
\\begin{{tabular}}{{{columns}}}
\\hline
{header} \\\\
\\hline
{body}
\\hline
\\end{{tabular}}
\\end{{table}}
"""


def _multiplier_note(core: pd.DataFrame) -> str:
    """Report the dependent-lag coefficient behind the long-run multiplier."""
    parts: list[str] = []
    for driver in ("productivity_per_worker", "productivity"):
        results = _verified_model_results(core, driver)
        if not results:
            continue
        coefficients = results.get("distributed_lag", {}).get("summary", {}).get("coefficients", [])
        gamma = next((c for c in coefficients if c.get("name") == "wage_l1"), None)
        if not gamma:
            continue
        value = float(gamma["estimate"])
        parts.append(
            rf"{_driver_label(driver)}: $\hat{{\gamma}}={_fmt_float(value)}$ "
            rf"(SE {_fmt_float(gamma['std_error'])}), so $1-\hat{{\gamma}}={_fmt_float(1.0 - value)}$"
        )
    if not parts:
        return ""
    return (
        " The multiplier is a ratio: " + "; ".join(parts) + ". "
        r"Each $|\hat{\gamma}|<1$, so the ratio is finite and the implied adjustment "
        "is stable, but its interval is a delta-method approximation. With a denominator "
        "estimated from the same small sample, that approximation degrades as "
        r"$1-\hat{\gamma}$ approaches zero; a Fieller \citep{fieller1954interval} or "
        "bootstrap interval would be "
        "a more reliable guide than the reported one."
    )


def _core_table(core: pd.DataFrame) -> str:
    required = {
        "driver",
        "role",
        "start_year",
        "end_year",
        "n_levels",
        "distributed_lag_cumulative",
        "distributed_lag_std_error",
        "distributed_lag_ci_low",
        "distributed_lag_ci_high",
        "distributed_lag_p_value",
    }
    missing = required.difference(core.columns)
    if missing:
        raise ValueError(f"core_estimates.csv missing columns: {sorted(missing)}")
    rows: list[str] = []
    for _, row in core.iterrows():
        driver = _escape_latex(_driver_label(str(row["driver"])))
        role = _escape_latex(str(row["role"]))
        period = f"{int(row['start_year'])}--{int(row['end_year'])}"
        estimate = _fmt_float(row["distributed_lag_cumulative"])
        se = _fmt_float(row["distributed_lag_std_error"])
        ci = f"[{_fmt_float(row['distributed_lag_ci_low'])}, {_fmt_float(row['distributed_lag_ci_high'])}]"
        p_value = _fmt_float(row["distributed_lag_p_value"])
        # n_levels is the input series length. The regression loses observations to
        # differencing and to two driver lags, so reporting it as N overstates the sample the
        # estimate actually rests on.
        results = _verified_model_results(core, str(row["driver"]))
        summary = (results or {}).get("distributed_lag", {}).get("summary", {})
        effective = summary.get("nobs")
        effective_text = str(int(effective)) if effective else "--"
        rows.append(
            f"{driver} ({role}) & {period} & {int(row['n_levels'])} & {effective_text} & "
            f"{estimate} & {se} & {ci} & {p_value} \\\\"
        )
    return _table_wrapper(
        caption="Pre-specified cumulative wage-transmission estimates.",
        label="tab:core-estimates",
        columns="p{3.1cm}rrrrrrr",
        header=("Driver & Period & Levels & Reg.\\ $N$ & $\\hat\\Theta$ & HAC SE & 95\\% CI & $p$"),
        rows=rows,
    )


# The growth regression loses one observation to differencing and two to the driver lags.
LOST_TO_LAGS = 3

MODEL_LABELS = {
    "ecm_long_run": "Error-correction long run",
    "state_space_latest": "State-space latest slope",
    "structural_breaks": "Structural breaks",
    "asymmetry": "Asymmetry",
    "local_projections": "Local projections",
}

GATE_LABELS = {
    "unsupported_without_cointegration": r"Cointegration unsupported at 5\%",
    "latest_slope_imprecise": "Latest slope not distinguishable from zero",
    "small_regime_segments": "Regime segments below interpretation threshold",
    "underpowered_shock_balance": "Too few shocks of the rarer sign",
    "long_horizons_exploratory": "Long horizons below effective sample",
}


def _model_estimate(core: pd.DataFrame, driver: str, model: str) -> str:
    """The estimate behind a gate row, so a reader can see what was gated."""
    matched = core.loc[core["driver"] == driver]
    if matched.empty:
        return "---"
    row = matched.iloc[0]
    if model == "ecm_long_run":
        return _fmt_float(row.get("ecm_long_run_elasticity"))
    if model == "state_space_latest":
        estimate = _fmt_float(row.get("state_space_latest"))
        error = _fmt_float(row.get("state_space_latest_std_error"))
        return f"{estimate} ({error})"
    if model == "structural_breaks":
        years = str(row.get("structural_break_years") or "").replace(";", ", ")
        return _escape_latex(years) if years else "none"
    if model == "asymmetry":
        positive = _fmt_float(row.get("asymmetry_positive_cumulative"))
        negative = _fmt_float(row.get("asymmetry_negative_cumulative"))
        return f"{positive} / {negative}"
    if model == "local_projections":
        # Horizons are not estimates. The coefficients have their own table.
        return r"see Table~\ref{tab:local-projections}"
    return "---"


def _reliability_table(reliability: pd.DataFrame, core: pd.DataFrame) -> str:
    required = {"driver", "model", "claim_eligible", "policy", "reason"}
    missing = required.difference(reliability.columns)
    if missing:
        raise ValueError(f"reliability_gates.csv missing columns: {sorted(missing)}")
    rows: list[str] = []
    for _, row in reliability.iterrows():
        driver = str(row["driver"])
        model = str(row["model"])
        eligible = "eligible" if _bool_value(row["claim_eligible"]) else "not eligible"
        eligible_cell = _escape_latex(eligible)
        if model == "state_space_latest":
            # This model carries no eligibility verdict. What was recorded against it is a
            # significance threshold, which decides nothing about reliability.
            eligible_cell = _escape_latex("inconclusive")
        if model == "local_projections" and _bool_value(row["claim_eligible"]):
            # The gate passes only for the shorter horizons; a bare "eligible" overstates it.
            eligible_cell = _escape_latex(eligible) + r", $h \le 3$"
        reason = str(row["reason"])
        rows.append(
            "{} & {} & {} & {} & {} \\\\".format(
                _escape_latex(_driver_label(driver)),
                _escape_latex(MODEL_LABELS.get(model, model.replace("_", " "))),
                _model_estimate(core, driver, model),
                eligible_cell,
                GATE_LABELS.get(reason, _escape_latex(reason)),
            )
        )
    return _table_wrapper(
        caption="Supporting models, their estimates, and their pre-specified eligibility rules.",
        label="tab:reliability-gates",
        columns="P{2.5cm}P{2.2cm}lP{2.0cm}P{4.4cm}",
        header="Driver & Model & Estimate & Claim status & Gate result",
        rows=rows,
    )


def _country_estimates_table(cross: pd.DataFrame, dossier_dir: Path) -> str | None:
    """Render every country-specific estimate, not merely their summary.

    The surrounding text calls the country-specific estimates the primary cross-country object,
    so publishing only a median and a random-effects summary would contradict it. The estimates
    are read from the path the dossier recorded, and its digest is checked, so this table is as
    traceable as the summary it accompanies.
    """
    if "country_estimates_path" not in cross.columns:
        return None
    primary = cross.loc[cross["driver"] == "productivity_per_worker"]
    if primary.empty:
        return None
    row = primary.iloc[0]
    path = Path(str(row["country_estimates_path"]))
    if not path.is_file():
        path = dossier_dir / path.name
    if not path.is_file():
        return None

    recorded = str(row.get("country_estimates_sha256") or "")
    if recorded and sha256_file(path) != recorded:
        raise ValueError(
            f"Country estimates at {path} do not match the digest recorded in the dossier. "
            "The table would not correspond to the verified run."
        )

    estimates = pd.read_csv(path)
    needed = {"country", "distributed_lag_cumulative", "distributed_lag_cumulative_se", "nobs"}
    has_cointegration = "cointegration_p_value" in estimates.columns
    missing = needed.difference(estimates.columns)
    if missing:
        raise ValueError(f"Country estimates missing columns: {sorted(missing)}")

    estimates = estimates.sort_values("distributed_lag_cumulative")
    rows: list[str] = []
    for _, item in estimates.iterrows():
        estimate = float(item["distributed_lag_cumulative"])
        error = float(item["distributed_lag_cumulative_se"])
        low, high = estimate - 1.96 * error, estimate + 1.96 * error
        country = _escape_latex(str(item["country"]))
        if str(item["country"]) == "PRT":
            country = r"\textbf{PRT}"
        levels = int(item["nobs"])
        cells = [
            country,
            str(levels),
            str(levels - LOST_TO_LAGS),
            _fmt_float(estimate),
            _fmt_float(error),
            f"[{_fmt_float(low)}, {_fmt_float(high)}]",
        ]
        if has_cointegration:
            cells.append(_fmt_float(item["cointegration_p_value"]))
            cells.append("yes" if _bool_value(item.get("cointegration_5pct", False)) else "no")
        rows.append(" & ".join(cells) + r" \\")

    return _table_wrapper(
        caption="Country-specific cumulative transmission, GDP per person employed.",
        label="tab:country-estimates",
        columns="lrrrrr" + ("rl" if has_cointegration else ""),
        header=(
            r"Country & Levels & Reg.\ $N$ & Cumulative & HAC SE & 95\% CI"
            + (r" & EG $p$ & Coint.\ 5\%" if has_cointegration else "")
        ),
        rows=rows,
    )


def _verified_model_results(core: pd.DataFrame, driver: str) -> dict[str, Any] | None:
    """Load one driver's serialized model results, checking the digest the dossier recorded."""
    matched = core.loc[core["driver"] == driver]
    if matched.empty or "source_result_path" not in core.columns:
        return None
    row = matched.iloc[0]
    path = Path(str(row["source_result_path"]))
    if not path.is_file():
        return None
    recorded = str(row.get("source_result_sha256") or "")
    if recorded and sha256_file(path) != recorded:
        raise ValueError(
            f"Model results at {path} do not match the digest recorded in the dossier; "
            "a table built from them would not correspond to the verified run."
        )
    return _load_json_object(path)


def _local_projection_table(core: pd.DataFrame) -> str | None:
    """Render the local-projection responses horizon by horizon.

    Local projections are the only supporting model that passes its reliability gate, so
    reporting the gate verdict without the coefficients leaves the one interpretable supporting
    result invisible. Both interval types are shown: the asymptotic HAC interval and the
    block-bootstrap interval. The gap between them is the point, since overlapping windows leave
    a small effective sample at long horizons and the HAC interval does not know that.
    """
    collected: list[tuple[str, list[Any], dict[int, Any], set[int]]] = []
    for driver in ("productivity_per_worker", "productivity"):
        results = _verified_model_results(core, driver)
        if not results:
            continue
        points = results.get("local_projections") or []
        if not points:
            continue
        bands = {int(b["horizon"]): b for b in (results.get("local_projection_bands") or [])}
        matched = core.loc[core["driver"] == driver]
        supported: set[int] = set()
        if not matched.empty:
            raw = str(matched.iloc[0].get("supported_local_projection_horizons") or "")
            supported = {int(part) for part in raw.split(";") if part.strip().isdigit()}
        collected.append((driver, points, bands, supported))
    if not collected:
        return None

    rows: list[str] = []
    for driver, points, bands, supported in collected:
        for point in points:
            horizon = int(point["horizon"])
            band = bands.get(horizon)
            bootstrap = (
                f"[{_fmt_float(band['lower_95'])}, {_fmt_float(band['upper_95'])}]"
                if band
                else "--"
            )
            marker = "" if horizon in supported else r"$^{\dagger}$"
            rows.append(
                "{} & {}{} & {} & {} & [{}, {}] & {} & {} \\\\".format(
                    _escape_latex(_driver_label(driver)),
                    horizon,
                    marker,
                    _fmt_float(point["estimate"]),
                    _fmt_float(point["std_error"]),
                    _fmt_float(point["lower_95"]),
                    _fmt_float(point["upper_95"]),
                    bootstrap,
                    int(point["nobs"]),
                )
            )

    return _table_wrapper(
        caption="Local-projection responses of real wages to productivity growth.",
        label="tab:local-projections",
        columns="p{2.9cm}rrrrrr",
        header=(r"Driver & Horizon & Estimate & HAC SE & HAC 95\% CI & Bootstrap 95\% CI & $n$"),
        rows=rows,
    )


def _forest_plot(cross: pd.DataFrame, dossier_dir: Path, output: Path) -> Path | None:
    """Plot every country estimate against the random-effects summary.

    A thirteen-row table states the estimates; a forest plot shows whether they overlap, which
    is the question the heterogeneity statistic answers numerically.
    """
    if "country_estimates_path" not in cross.columns:
        return None
    primary = cross.loc[cross["driver"] == "productivity_per_worker"]
    if primary.empty:
        return None
    row = primary.iloc[0]
    path = Path(str(row["country_estimates_path"]))
    if not path.is_file():
        path = dossier_dir / path.name
    if not path.is_file():
        return None

    import matplotlib

    matplotlib.use("Agg")
    # Type 3 fonts are rejected by some submission systems; 42 embeds TrueType.
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    import matplotlib.pyplot as plt

    estimates = pd.read_csv(path).sort_values("distributed_lag_cumulative")
    values = estimates["distributed_lag_cumulative"].to_numpy(dtype=float)
    errors = estimates["distributed_lag_cumulative_se"].to_numpy(dtype=float)
    labels = [str(value) for value in estimates["country"]]
    positions = range(len(values))

    summary = float(row["random_effect_estimate"])

    figure, axes = plt.subplots(figsize=(6.4, 0.34 * len(values) + 1.6))
    for index, (estimate, error, label) in enumerate(zip(values, errors, labels, strict=True)):
        highlight = label == "PRT"
        axes.plot(
            [estimate - 1.96 * error, estimate + 1.96 * error],
            [index, index],
            color="#b03030" if highlight else "#444444",
            linewidth=2.0 if highlight else 1.2,
            solid_capstyle="butt",
        )
        axes.plot(
            [estimate],
            [index],
            marker="s" if highlight else "o",
            color="#b03030" if highlight else "#222222",
            markersize=6 if highlight else 4.5,
        )

    axes.axvline(0.0, color="#888888", linewidth=0.9, linestyle=":")
    axes.axvline(1.0, color="#888888", linewidth=0.9, linestyle="--")
    # No band around the random-effects summary. A shaded interval reads as inference, and this
    # one would rest on the independence assumption the paper questions. The median needs no such
    # assumption, so it carries the reference line and the summary keeps a thin marker.
    median = float(pd.Series(values).median())
    axes.axvline(median, color="#3060a0", linewidth=1.4)
    axes.axvline(summary, color="#3060a0", linewidth=0.8, linestyle="-.", alpha=0.75)

    axes.set_yticks(list(positions))
    axes.set_yticklabels(labels)
    axes.set_ylim(-0.8, len(values) - 0.2)
    axes.set_xlabel("Cumulative transmission of productivity growth into real wages")
    axes.set_title("Country-specific estimates, with the median country", fontsize=10)
    axes.text(
        median,
        len(values) - 0.55,
        f"  median {median:.3f}",
        color="#3060a0",
        fontsize=8,
        va="center",
    )
    axes.text(
        summary,
        len(values) - 1.35,
        f"  RE {summary:.3f}",
        color="#3060a0",
        fontsize=7,
        alpha=0.85,
        va="center",
    )
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Omit the wall-clock stamp: the figure is hashed into the packet manifest and
    # embedded in the PDF, so its bytes must not depend on when it was drawn.
    figure.savefig(output, bbox_inches="tight", metadata={"CreationDate": None})
    plt.close(figure)
    return output


def _verified_summary(cross: pd.DataFrame, dossier_dir: Path, driver: str) -> dict[str, Any]:
    """Read one driver's cross-country summary JSON, checking the digest the dossier recorded.

    The dossier CSV carries the headline summary numbers but not every field the estimator
    produced. Rather than widen the locked dossier writer after results were seen, the extra
    fields are read from the artefact the dossier already points at and hashes.
    """
    matched = cross.loc[cross["driver"] == driver]
    if matched.empty or "summary_path" not in cross.columns:
        return {}
    row = matched.iloc[0]
    path = Path(str(row["summary_path"]))
    if not path.is_file():
        path = dossier_dir / path.name
    if not path.is_file():
        return {}
    recorded = str(row.get("summary_sha256") or "")
    if recorded and sha256_file(path) != recorded:
        raise ValueError(
            f"Cross-country summary at {path} does not match the digest recorded in the dossier."
        )
    return _load_json_object(path)


def _cross_country_table(cross: pd.DataFrame, dossier_dir: Path) -> str:
    required = {
        "driver",
        "n_countries",
        "median_cumulative_transmission",
        "random_effect_estimate",
        "random_effect_std_error",
        "i_squared_percent",
    }
    missing = required.difference(cross.columns)
    if missing:
        raise ValueError(f"cross_country_summary.csv missing columns: {sorted(missing)}")
    rows: list[str] = []
    for _, row in cross.iterrows():
        driver = str(row["driver"])
        summary = _verified_summary(cross, dossier_dir, driver)
        rows.append(
            "{} & {} & {} & {} & {} & {} & {}\\% \\\\".format(
                _escape_latex(_driver_label(driver)),
                int(row["n_countries"]),
                _fmt_float(row["median_cumulative_transmission"]),
                _fmt_float(row["random_effect_estimate"]),
                _fmt_float(row["random_effect_std_error"]),
                _fmt_float(summary.get("tau_squared"), 4),
                _fmt_float(row["i_squared_percent"], 1),
            )
        )
    return _table_wrapper(
        caption="Cross-country context for cumulative wage transmission.",
        label="tab:cross-country",
        columns="lrrrrrr",
        header=r"Driver & Countries & Median & RE estimate & RE SE & $\tau^2$ & $I^2$",
        rows=rows,
    )


def _decomposition_table(decomposition: pd.DataFrame) -> str:
    """Render the accounting components.

    The component column names must match what the dossier writes. Earlier this function
    filtered to whichever recognised columns happened to be present, so a rename upstream
    degraded the table to country, years and residual without any error -- a caption promising
    a decomposition above a table containing none. Missing components now raise.
    """
    if decomposition.empty:
        return "% AUTO-GENERATED. No decomposition rows were available.\n"

    components = {
        "real_gdp_log_contribution": "Real GDP",
        "labour_share_log_contribution": r"$\Delta$ labour share",
        "employment_log_contribution": "Employees",
        "relative_price_log_contribution": "Price wedge",
    }
    required = {"country", "start_year", "end_year", "observed_real_wage_log_change", *components}
    missing = required.difference(decomposition.columns)
    if missing:
        raise ValueError(
            "decomposition_summary.csv is missing publication columns: "
            f"{sorted(missing)}. The dossier schema and this formatter have drifted apart; "
            "a decomposition table without its components must not be published."
        )

    rows: list[str] = []
    for _, row in decomposition.iterrows():
        cells = [
            _escape_latex(str(row["country"])),
            _escape_latex(f"{int(row['start_year'])}--{int(row['end_year'])}"),
            _fmt_float(row["observed_real_wage_log_change"]),
        ]
        cells.extend(_fmt_float(row[column]) for column in components)
        residual = row.get("max_abs_identity_residual")
        cells.append("$<10^{-9}$" if float(residual or 0.0) < 1e-9 else _fmt_float(residual, 2))
        rows.append(" & ".join(cells) + " \\\\")

    header = "Country & Period & Observed & " + " & ".join(components.values()) + " & Residual"
    return _table_wrapper(
        caption="Accounting decomposition of real compensation per employee (log points).",
        label="tab:decomposition",
        columns="ll" + "r" * (len(components) + 2),
        header=header,
        rows=rows,
    )


def _decomposition_appendix(decomposition: pd.DataFrame, *, minimum_countries: int = 11) -> str:
    """Render every country's decomposition, so the coverage claim is verifiable.

    The main-text table shows the primary country. This one shows all of them, because a paper
    stating that the decomposition covers N countries should let a reader count them.

    Two guards. Countries are never silently dropped: fewer rows than expected raises rather than
    quietly narrowing the evidence behind a coverage claim. And cumulative log changes over
    different periods are not comparable, so a mixed-period set gains an annualised column rather
    than being presented as though the totals could be read side by side.
    """
    if decomposition.empty:
        return ""
    components = {
        "real_gdp_log_contribution": "Real GDP",
        "labour_share_log_contribution": r"$\Delta$ share",
        "employment_log_contribution": "Employees",
        "relative_price_log_contribution": "Prices",
    }
    required = {"country", "start_year", "end_year", "observed_real_wage_log_change", *components}
    missing = required.difference(decomposition.columns)
    if missing:
        raise ValueError(f"Decomposition appendix is missing columns: {sorted(missing)}")
    if len(decomposition) < minimum_countries:
        raise ValueError(
            f"Decomposition appendix expected at least {minimum_countries} countries, got "
            f"{len(decomposition)}: {sorted(decomposition['country'])}. Countries must not "
            "disappear from a coverage claim without the build failing."
        )

    periods = set(zip(decomposition["start_year"], decomposition["end_year"], strict=True))
    common_period = len(periods) == 1
    frame = decomposition.sort_values("observed_real_wage_log_change", ascending=False)

    rows: list[str] = []
    for _, row in frame.iterrows():
        span = max(int(row["end_year"]) - int(row["start_year"]), 1)
        cells = [_escape_latex(str(row["country"]))]
        if not common_period:
            cells.append(f"{int(row['start_year'])}--{int(row['end_year'])}")
        cells.append(_fmt_float(row["observed_real_wage_log_change"]))
        if not common_period:
            cells.append(_fmt_float(float(row["observed_real_wage_log_change"]) / span, 4))
        cells.extend(_fmt_float(row[column]) for column in components)
        residual = float(row.get("max_abs_identity_residual") or 0.0)
        cells.append("$<10^{-9}$" if residual < 1e-9 else _fmt_float(residual, 2))
        rows.append(" & ".join(cells) + r" \\")

    header = ["Country"]
    columns = "l"
    if not common_period:
        header.append("Period")
        columns += "l"
    header.append("Observed")
    columns += "r"
    if not common_period:
        header.append("Annualised")
        columns += "r"
    header.extend(components.values())
    header.append("Residual")
    columns += "r" * (len(components) + 1)

    return _table_wrapper(
        caption="Accounting decomposition by country (log points).",
        label="tab:decomposition-appendix",
        columns=columns,
        header=" & ".join(header),
        rows=rows,
    )


SOURCE_PURPOSES = {
    "average_wages": "Real annual wages, dependent employees (FTE)",
    "productivity_per_hour": "Secondary driver: GDP per hour worked",
    "productivity_per_worker": "Primary driver: GDP per person employed",
    "real_gdp": "Decomposition: chain-linked real GDP",
    "nominal_gdp": "Decomposition: nominal GDP",
    "employee_compensation": "Decomposition: compensation of employees",
    "employees": "Decomposition: employees, domestic concept",
    "consumer_price_index": "Decomposition: all-items annual average HICP",
}


def _source_table(config_path: Path) -> str | None:
    """Tabulate the dataflow identifiers, which clutter prose but belong on record.

    Readers need the exact identifiers to reproduce a retrieval, and a sentence carrying an SDMX
    dataflow reference is unreadable. The table is generated from the configuration the download
    layer actually uses, so it cannot drift from what was retrieved.
    """
    if not config_path.is_file():
        return None
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return None

    rows: list[str] = []
    for name, spec in (config.get("oecd") or {}).items():
        if not isinstance(spec, dict) or "flow_ref" not in spec:
            continue
        if str(spec.get("status", "")).lower() == "unverified":
            continue
        # The key template is what selects the series; ``measure`` only names it. Printing the
        # template is what lets a reader reissue the request.
        selection = str(spec.get("key_template") or spec.get("measure") or "--")
        rows.append(
            "OECD & {} & {} & {} \\\\".format(
                _escape_latex(str(spec["flow_ref"])),
                _escape_latex(selection),
                _escape_latex(SOURCE_PURPOSES.get(name, name.replace("_", " "))),
            )
        )
    for name, spec in (config.get("eurostat") or {}).items():
        if not isinstance(spec, dict) or "dataset" not in spec:
            continue
        filters = spec.get("filters") or {}
        if not filters:
            # No filters means the download layer never issues a request for it, so listing it
            # would advertise a series the paper does not use.
            continue
        detail = ", ".join(f"{key}={value}" for key, value in filters.items())
        rows.append(
            "Eurostat & {} & {} & {} \\\\".format(
                _escape_latex(str(spec["dataset"])),
                _escape_latex(detail or "--"),
                _escape_latex(SOURCE_PURPOSES.get(name, name.replace("_", " "))),
            )
        )
    if not rows:
        return None

    return _table_wrapper(
        caption="Official source identifiers.",
        label="tab:sources",
        columns="lp{3.6cm}p{3.9cm}p{3.3cm}",
        header="Provider & Dataset or dataflow & Selection & Use",
        rows=rows,
    )


def _break_table(core: pd.DataFrame) -> str | None:
    """Report the break evidence, which the text describes but no table carried.

    Two procedures answer different questions and are reported side by side. The BIC
    segmentation asks how many regimes fit best and always returns a partition; the sup-F test
    asks whether there is evidence of a break at all, and can answer no. Reporting the selected
    dates without the test invites the first to be read as the second.
    """
    rows: list[str] = []
    for driver in ("productivity_per_worker", "productivity"):
        results = _verified_model_results(core, driver)
        if not results:
            continue
        inference = results.get("break_inference")
        if not inference:
            continue
        segmentation = results.get("structural_breaks") or {}
        reliability = results.get("reliability") or {}
        bic_years = ", ".join(str(year) for year in segmentation.get("break_years") or []) or "none"
        rows.append(
            "{} & {} & {} & {} & {} & [{}, {}] & {} & {} \\\\".format(
                _escape_latex(_driver_label(driver)),
                _escape_latex(bic_years),
                int(inference["break_year"]),
                _fmt_float(inference["sup_f"], 2),
                _fmt_float(inference["p_value"]),
                int(inference["break_year_lower"]),
                int(inference["break_year_upper"]),
                int(reliability.get("structural_break_smallest_segment") or 0),
                _escape_latex(
                    "not eligible"
                    if not _bool_value(
                        core.loc[core["driver"] == driver, "structural_break_claim_eligible"].iloc[
                            0
                        ]
                    )
                    else "eligible"
                ),
            )
        )
    if not rows:
        return None

    return _table_wrapper(
        caption="Structural-break evidence: BIC segmentation and the sup-F test.",
        label="tab:breaks",
        columns="p{2.6cm}lrrrlrl",
        header=(
            r"Driver & BIC breaks & sup-$F$ date & sup-$F$ & $p$ & Date interval & "
            r"Min.\ segment & Gate"
        ),
        rows=rows,
    )


_FIXED_EFFECT_LABEL = {
    "country_and_year": "Country + year",
    "country": "Country only",
}

_ESTIMATOR_LABEL = {"lsdv": "LSDV", "corrected": "LSDVC"}


def _clopper_pearson(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval for a coverage proportion."""
    if trials <= 0:
        return (float("nan"), float("nan"))
    lower = (
        0.0 if successes <= 0 else float(beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    )
    upper = (
        1.0
        if successes >= trials
        else float(beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    )
    return (lower, upper)


def _wilson_interval(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Used as the input to the difference interval rather than reported on its own. Its behaviour
    near zero and one is what makes the difference interval usable there.
    """
    if trials <= 0:
        return (float("nan"), float("nan"))
    from scipy.stats import norm

    z = float(norm.ppf(1.0 - alpha / 2.0))
    share = successes / trials
    denominator = 1.0 + z**2 / trials
    centre = (share + z**2 / (2.0 * trials)) / denominator
    half = z / denominator * math.sqrt(share * (1.0 - share) / trials + z**2 / (4.0 * trials**2))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _newcombe_difference(
    successes_a: int,
    trials_a: int,
    successes_b: int,
    trials_b: int,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Newcombe's hybrid score interval for the difference between two proportions.

    The two coverage studies draw independent panels, so this is a two-sample interval and not a
    paired one. Its endpoints come from the Wilson intervals of the two proportions, which is what
    keeps it honest when one of them sits close to one.
    """
    if trials_a <= 0 or trials_b <= 0:
        return (float("nan"), float("nan"))
    share_a = successes_a / trials_a
    share_b = successes_b / trials_b
    low_a, high_a = _wilson_interval(successes_a, trials_a, alpha)
    low_b, high_b = _wilson_interval(successes_b, trials_b, alpha)
    difference = share_a - share_b
    lower = difference - math.sqrt((share_a - low_a) ** 2 + (high_b - share_b) ** 2)
    upper = difference + math.sqrt((high_a - share_a) ** 2 + (share_b - low_b) ** 2)
    return (lower, upper)


def _coverage_successes(row: Mapping[str, Any], prefix: str = "percentile") -> tuple[int, int]:
    """The success and trial counts behind a recorded coverage proportion."""
    trials = int(row.get("completed") or row.get("replications") or 0)
    share = float(row[f"{prefix}_coverage"])
    return (round(share * trials), trials)


def _coverage_cell(row: Mapping[str, Any], prefix: str) -> str:
    """A coverage proportion with its exact Monte Carlo interval.

    Older validation artefacts record the proportion and the number of completed draws but not
    the interval. The interval is a function of exactly those two numbers, so it is recomputed
    rather than omitted: a note that promises brackets must not print a bare percentage.
    """
    share = float(row[f"{prefix}_coverage"])
    point = _fmt_pct_fraction(share)
    interval = row.get(f"{prefix}_coverage_ci")
    if not isinstance(interval, list) or len(interval) != 2:
        trials = int(row.get("completed") or 0)
        if trials <= 0:
            return point
        interval = list(_clopper_pearson(round(share * trials), trials))
    low = _fmt_pct_fraction(interval[0])
    high = _fmt_pct_fraction(interval[1])
    return f"{point} [{low}, {high}]"


def _has_finite(entry: Mapping[str, Any], key: str) -> bool:
    """Whether a recorded statistic is present and usable."""
    value = entry.get(key)
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _statistic_cell(entry: Mapping[str, Any], key: str) -> str:
    """A simulated statistic with the standard error of its mean, when one was recorded."""
    point = _fmt_float(entry.get(key))
    error = entry.get(f"{key}_se")
    if error is None or not isinstance(error, (int, float)) or not math.isfinite(float(error)):
        return point
    return f"{point} ({_fmt_float(error, 4)})"


def _benchmark_payload(dossier_dir: Path) -> dict[str, Any]:
    """The design record, if the benchmark run has produced one."""
    path = dossier_dir / "dynamic_panel_benchmark.json"
    if not path.is_file():
        return {}
    return _load_json_object(path)


def _coverage_interval(row: Mapping[str, Any]) -> tuple[float, float]:
    """The Monte Carlo interval for a percentile-coverage estimate."""
    interval = row.get("percentile_coverage_ci")
    if isinstance(interval, list) and len(interval) == 2:
        return (float(interval[0]), float(interval[1]))
    share = float(row["percentile_coverage"])
    trials = int(row.get("completed") or row.get("replications") or 0)
    if trials <= 0:
        return (share, share)
    return _clopper_pearson(round(share * trials), trials)


def _benchmark_prose(dossier_dir: Path) -> str:
    """Interpret the independent-error benchmark, one persistence at a time."""
    benchmark = _benchmark_payload(dossier_dir)
    independent = benchmark.get("independent_coverage_study") or []
    path = dossier_dir / "dynamic_panel_validation.json"
    if not independent or not path.is_file():
        return ""
    dependent = {
        float(row["true_persistence"]): row
        for row in _load_json_object(path).get("coverage_study") or []
    }

    nominal = 0.95
    findings: list[str] = []
    for entry in sorted(independent, key=lambda row: float(row["true_persistence"])):
        gamma = float(entry["true_persistence"])
        paired = dependent.get(gamma)
        if paired is None:
            continue
        # Falling short of nominal is a one-sample question; the marginal interval answers it.
        dependent_short = _coverage_interval(paired)[1] < nominal
        independent_short = _coverage_interval(entry)[1] < nominal
        # Whether the two designs differ is a two-sample question, and needs the difference.
        dependent_successes, dependent_trials = _coverage_successes(paired)
        independent_successes, independent_trials = _coverage_successes(entry)
        low, high = _newcombe_difference(
            dependent_successes, dependent_trials, independent_successes, independent_trials
        )
        differ = low > 0.0 or high < 0.0

        label = f"At $\\gamma={_fmt_float(gamma, 2)}$"
        if not dependent_short and not independent_short:
            findings.append(
                f"{label} neither design shows a shortfall distinguishable from the nominal level."
            )
        elif dependent_short and not independent_short and differ:
            findings.append(
                f"{label} the benchmark shows no distinguishable shortfall while the dependent "
                "design does, and the two differ, so what the interval loses there it loses to "
                "cross-sectional dependence."
            )
        elif dependent_short and independent_short and not differ:
            findings.append(
                f"{label} both designs fall short and their difference cannot be distinguished "
                "from zero, so the shortfall there belongs to the resampling scheme and dependence "
                "is not shown to add to it."
            )
        elif differ:
            findings.append(
                f"{label} the two designs differ, so dependence changes the coverage attained."
            )
        else:
            findings.append(
                f"{label} the difference between the designs cannot be distinguished from zero, so "
                "dependence is not shown to change the coverage attained."
            )
    if not findings:
        return ""

    return (
        "Table~\\ref{tab:validation-benchmark} separates the two mechanisms that can push the "
        "interval below its nominal level. Removing the common factor while holding each "
        "country's total error variance at $c_i^2+d_i^2$ changes the dependence and nothing else, "
        "so the difference between the columns is what dependence contributes and the remaining "
        "shortfall is what the resampling scheme contributes. Whether a design falls short is read "
        "from its own interval; whether two designs differ is read from the interval for their "
        "difference, since overlapping marginal intervals settle nothing. "
        + " ".join(findings)
        + " No separate arm is run for the design carrying one disturbance common to every "
        "country, because Table~\\ref{tab:validation-dependence} shows it is indistinguishable "
        "from independent errors once country and year means are swept out."
    )


def _benchmark_coverage_table(dossier_dir: Path) -> tuple[str, str] | None:
    """Coverage under the dependent design beside coverage under independent errors."""
    benchmark = _benchmark_payload(dossier_dir)
    independent = benchmark.get("independent_coverage_study") or []
    if not independent:
        return None
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return None
    dependent = _load_json_object(path).get("coverage_study") or []
    if not dependent:
        return None

    by_persistence = {float(row["true_persistence"]): row for row in dependent}
    rows: list[str] = []
    for entry in independent:
        gamma = float(entry["true_persistence"])
        paired = by_persistence.get(gamma)
        if paired is None:
            continue
        dependent_successes, dependent_trials = _coverage_successes(paired)
        independent_successes, independent_trials = _coverage_successes(entry)
        difference = float(paired["percentile_coverage"]) - float(entry["percentile_coverage"])
        low, high = _newcombe_difference(
            dependent_successes, dependent_trials, independent_successes, independent_trials
        )
        difference_cell = (
            f"{_fmt_float(100.0 * difference, 1)} pp "
            f"[{_fmt_float(100.0 * low, 1)}, {_fmt_float(100.0 * high, 1)}]"
        )
        rows.append(
            "{} & {} & {} & {} \\\\".format(
                _fmt_float(gamma, 2),
                _coverage_cell(paired, "percentile"),
                _coverage_cell(entry, "percentile"),
                difference_cell,
            )
        )
    if not rows:
        return None
    return (
        "table_validation_benchmark.tex",
        _table_wrapper(
            caption=(
                "Coverage of the nominal 95\\% percentile interval under the dependent error "
                "design and under independent errors of the same total variance. The difference "
                "is in percentage points, with a Newcombe hybrid score interval for two "
                "independent samples."
            ),
            label="tab:validation-benchmark",
            columns="rlll",
            header=("True $\\gamma$ & Dependent errors & Independent errors & Difference"),
            rows=rows,
        ),
    )


def _design_tables(dossier_dir: Path) -> list[tuple[str, str]]:
    """Render the calibrated error design and the dependence each candidate design leaves."""
    payload = _benchmark_payload(dossier_dir)
    if not payload:
        return []
    tables: list[tuple[str, str]] = []

    countries = payload.get("countries") or []
    if countries:
        rows = [
            "{} & {} & {} & {} \\\\".format(
                _escape_latex(str(entry.get("country", entry.get("index")))),
                _fmt_float(entry["loading"], 4),
                _fmt_float(entry["idiosyncratic_sd"], 4),
                _fmt_pct_fraction(entry["factor_variance_share"]),
            )
            for entry in countries
        ]
        tables.append(
            (
                "table_validation_design.tex",
                _table_wrapper(
                    caption=(
                        "Calibrated error design for the simulation: factor loading, "
                        "idiosyncratic scale and the factor's share of each country's error "
                        "variance."
                    ),
                    label="tab:validation-design",
                    columns="lrrr",
                    header=("Country & Loading $c_i$ & Idiosyncratic $d_i$ & Factor share"),
                    rows=rows,
                ),
            )
        )

    dependence = payload.get("dependence") or {}
    design_labels = [
        ("factor", "Factor, heterogeneous loadings (used)"),
        ("equicorrelated", "One disturbance common to all"),
        ("independent", "Independent errors"),
    ]
    rows = []
    for key, label in design_labels:
        entry = dependence.get(key) or {}
        if not entry:
            continue
        rows.append(
            "{} & {} & {} & {} & {} \\\\".format(
                _escape_latex(label),
                _statistic_cell(entry, "raw_mean_absolute_correlation"),
                _statistic_cell(entry, "within_mean_absolute_correlation"),
                _statistic_cell(entry, "raw_leading_eigenvalue_share"),
                _statistic_cell(entry, "within_leading_eigenvalue_share"),
            )
        )
    observed_absolute = dependence.get("observed_within_mean_absolute_correlation")
    observed_leading = dependence.get("observed_within_leading_eigenvalue_share")
    if rows and observed_absolute is not None:
        rows.append(
            "{} & {} & {} & {} & {} \\\\".format(
                _escape_latex("Observed within residuals"),
                "---",
                _fmt_float(observed_absolute),
                "---",
                _fmt_float(observed_leading),
            )
        )
    replications = int(dependence.get("replications") or 0)
    # Promise the standard errors only if they are actually printed. The cells fall back to a bare
    # mean when the artefact predates the field, and a caption must not describe a missing column.
    has_errors = any(
        _has_finite(dependence.get(key) or {}, f"{side}_{statistic}_se")
        for key, _ in design_labels
        for side in ("raw", "within")
        for statistic in ("mean_absolute_correlation", "leading_eigenvalue_share")
    )
    if replications and has_errors:
        suffix = (
            f" Simulated rows are means over {replications} drawn panels, with the standard error "
            "of the mean in parentheses. The observed row is computed once, from the estimated "
            "residuals."
        )
    elif replications:
        suffix = (
            f" Simulated rows are means over {replications} drawn panels. The observed row is "
            "computed once, from the estimated residuals."
        )
    else:
        suffix = ""
    if rows:
        tables.append(
            (
                "table_validation_dependence.tex",
                _table_wrapper(
                    caption=(
                        "Cross-country dependence left by each candidate error design, before "
                        "and after country and year means are swept out." + suffix
                    ),
                    label="tab:validation-dependence",
                    columns="P{4.3cm}rrrr",
                    header=(
                        "Error design & $|\\rho|$ raw & $|\\rho|$ within & "
                        "Lead.\\ raw & Lead.\\ within"
                    ),
                    rows=rows,
                ),
            )
        )
    return tables


def _validation_tables(dossier_dir: Path) -> list[tuple[str, str]]:
    """Render the Monte Carlo evidence for the estimator and for its interval.

    The manuscript asserts that the bias correction works and that the percentile interval is
    usable despite a displaced resampling distribution. Neither can be checked from the
    estimates, so both are measured against panels with known parameters and reported here.
    """
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return []
    payload = _load_json_object(path)
    if payload.get("prespecified") is not False:
        raise ValueError(
            f"{path} does not record prespecified=false. This is a post-hoc validation study "
            "and must not be presented as part of the confirmatory hierarchy."
        )
    tables: list[tuple[str, str]] = []

    bias_rows = payload.get("bias_study") or []
    if bias_rows:
        rows = [
            "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                _fmt_float(row["true_persistence"], 2),
                _fmt_float(row["true_multiplier"]),
                _fmt_float(row["lsdv_persistence_bias"], 4),
                _fmt_float(row["nickell_approximation"], 4),
                _fmt_float(row["corrected_persistence_bias"], 4),
                _fmt_pct_fraction(row["persistence_bias_removed"]),
                _fmt_float(row["corrected_multiplier_bias"], 4),
                int(row["completed"]),
            )
            for row in bias_rows
        ]
        tables.append(
            (
                "table_validation_bias.tex",
                _table_wrapper(
                    caption=(
                        "Monte Carlo bias of the dynamic panel estimator, at the estimation "
                        "sample's dimensions."
                    ),
                    label="tab:validation-bias",
                    columns="rrrrrrrr",
                    header=(
                        r"True $\gamma$ & True $\Theta$ & LSDV bias & $-(1+\gamma)/T$ & "
                        r"LSDVC bias & Removed & LSDVC $\Theta$ bias & Draws"
                    ),
                    rows=rows,
                    size="scriptsize",
                ),
            )
        )

    coverage_rows = payload.get("coverage_study") or []
    if coverage_rows:
        rows = [
            "{} & {} & {} & {} & {} & {} & {} \\\\".format(
                _fmt_float(row["true_persistence"], 2),
                _fmt_float(row["true_multiplier"]),
                _coverage_cell(row, "percentile"),
                _coverage_cell(row, "reverse_percentile"),
                _fmt_float(row["percentile_mean_width"]),
                _fmt_float(row["median_displacement"], 4),
                int(row["completed"]),
            )
            for row in coverage_rows
        ]
        tables.append(
            (
                "table_validation_coverage.tex",
                _table_wrapper(
                    caption=(
                        "Monte Carlo coverage of the moving-block bootstrap intervals for "
                        "$\\Theta_{\\mathrm{panel}}$."
                    ),
                    label="tab:validation-coverage",
                    columns="rrllrrr",
                    header=(
                        r"True $\gamma$ & True $\Theta$ & Percentile coverage & "
                        r"Reverse coverage & Width & Displacement & Draws"
                    ),
                    rows=rows,
                    size="scriptsize",
                ),
            )
        )
    return tables


def _reverse_interval(record: pd.Series) -> str:
    """Reverse-percentile (basic) interval, reflecting the draws about the point estimate."""
    estimate = float(record["corrected_multiplier"])
    low = float(record["corrected_multiplier_ci_low"])
    high = float(record["corrected_multiplier_ci_high"])
    return f"$[{_fmt_float(2.0 * estimate - high)},\\ {_fmt_float(2.0 * estimate - low)}]$"


def _dynamic_panel_table(dossier_dir: Path) -> str | None:
    """Render the frozen dynamic panel: the same cumulative multiplier, estimated pooled.

    Both the uncorrected and the bias-corrected estimator appear, because the size of the
    correction is part of the evidence. Only the corrected row is substantive; the note says so,
    and the gate column says whether even that may be read as a result.
    """
    path = dossier_dir / "dynamic_panel_summary.csv"
    if not path.is_file():
        return None
    frame = pd.read_csv(path)
    reported = frame.loc[frame["role"].isin(["primary", "sensitivity_fixed_effects"])]
    if reported.empty:
        return None

    calibrated = _interval_is_calibrated(dossier_dir)
    rows: list[str] = []
    for driver in ("productivity_per_worker", "productivity"):
        for effects in ("country_and_year", "country"):
            matched = reported.loc[
                (reported["driver"] == driver) & (reported["fixed_effects"] == effects)
            ]
            if matched.empty:
                continue
            record = matched.iloc[0]
            for prefix in ("lsdv", "corrected"):
                interval = (
                    f"[{_fmt_float(record[f'{prefix}_multiplier_ci_low'])}, "
                    f"{_fmt_float(record[f'{prefix}_multiplier_ci_high'])}]"
                )
                persistence = (
                    record["corrected_persistence"]
                    if prefix == "corrected"
                    else record["lsdv_persistence"]
                )
                driver_sum = (
                    record["corrected_driver_sum"]
                    if prefix == "corrected"
                    else record["lsdv_driver_sum"]
                )
                gate = _gate_label(_bool_value(record["claim_eligible"]), calibrated)
                rows.append(
                    "{} & {} & {} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                        _escape_latex(_driver_label(driver)),
                        _escape_latex(_FIXED_EFFECT_LABEL.get(str(effects), str(effects))),
                        _ESTIMATOR_LABEL[prefix],
                        int(record["n_countries"]),
                        int(record["nobs"]),
                        _fmt_float(persistence),
                        _fmt_float(driver_sum),
                        _fmt_float(record[f"{prefix}_multiplier"]),
                        interval,
                        _escape_latex(gate),
                    )
                )
    if not rows:
        return None

    return _table_wrapper(
        caption=(
            "Dynamic panel: cumulative transmission "
            "$\\Theta_{\\mathrm{panel}}=(\\sum_j\\hat{\\beta}_j)/(1-\\hat{\\gamma})$. "
            "The intervals are nominal and unvalidated at the replication count reported here."
        ),
        label="tab:dynamic-panel",
        columns="p{1.75cm}p{1.35cm}lrrrrrlp{1.65cm}",
        header=(
            r"Driver & Fixed effects & Est. & Countries & Reg.\ $N$ & $\hat{\gamma}$ & "
            r"$\sum\hat{\beta}_j$ & $\hat{\Theta}$ & Nominal 95\% CI & Status"
        ),
        rows=rows,
        size="scriptsize",
    )


def _interval_is_calibrated(dossier_dir: Path) -> bool | None:
    """Whether the measured coverage reaches nominal, or None when it has not been measured.

    The comparison uses the upper end of the exact Monte Carlo interval, so a coverage estimate
    is only called a failure when the experiment can distinguish it from the nominal level.
    """
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return None
    rows = _load_json_object(path).get("coverage_study") or []
    if not rows:
        return None
    for row in rows:
        nominal = float(row["nominal_coverage"])
        interval = row.get("percentile_coverage_ci")
        upper = (
            float(interval[1])
            if isinstance(interval, list) and len(interval) == 2
            else float(row["percentile_coverage"])
        )
        if upper < nominal:
            return False
    return True


def _gate_label(claim_eligible: bool, calibrated: bool | None) -> str:
    """Report the estimation gate and the interval's calibration as the separate things they are."""
    if not claim_eligible:
        return "gate failed"
    if calibrated is not True:
        return "passed / not validated"
    return "passed / validated"


def _coverage_warning(dossier_dir: Path, persistence: float) -> str:
    """Quote the measured coverage at the simulated persistence closest to the estimate."""
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return (
            "Its coverage has not been measured on this vintage, so its nominal level should not "
            "be taken at face value. "
        )
    rows = _load_json_object(path).get("coverage_study") or []
    if not rows:
        return ""
    nearest = min(rows, key=lambda row: abs(float(row["true_persistence"]) - persistence))
    return (
        "Neither interval reaches its nominal level. Simulation at a true persistence of "
        f"{_fmt_float(nearest['true_persistence'], 2)}, closest to the estimate here, gives the "
        f"percentile interval {_fmt_pct_fraction(nearest['percentile_coverage'])} coverage and "
        f"the reverse-percentile interval "
        f"{_fmt_pct_fraction(nearest['reverse_percentile_coverage'])}, against a nominal "
        f"{_fmt_pct_fraction(nearest['nominal_coverage'])}. Both deteriorate as persistence "
        "rises. The simulation shows that these intervals do not attain nominal coverage under "
        "the evaluated designs, and it does not identify a valid scalar widening or an alternative "
        "calibrated interval. Appendix~\\ref{sec:validation} reports the full study. "
    )


def _dynamic_panel_note(frame: pd.DataFrame, dossier_dir: Path) -> str:
    """Everything a reader needs to interpret the table, generated from the same artefact."""
    primary = frame.loc[
        (frame["role"] == "primary") & (frame["driver"] == "productivity_per_worker")
    ]
    if primary.empty:
        primary = frame.loc[frame["role"] == "primary"]
    record = primary.iloc[0]

    sensitivity = frame.loc[frame["role"] == "sensitivity_block_length"]
    block_parts = [
        "block length {} gives $\\hat{{\\Theta}}={}$ [{}, {}]".format(
            int(row["block_length"]),
            _fmt_float(row["corrected_multiplier"]),
            _fmt_float(row["corrected_multiplier_ci_low"]),
            _fmt_float(row["corrected_multiplier_ci_high"]),
        )
        for _, row in sensitivity.loc[sensitivity["driver"] == str(record["driver"])]
        .sort_values("block_length")
        .iterrows()
    ]
    block_text = (
        "Prospectively specified block-length sensitivities on the primary driver: "
        + "; ".join(block_parts)
        + ". "
        if block_parts
        else " "
    )

    failures = sorted(
        {
            part
            for recorded in frame["gate_failures"].fillna("")
            for part in str(recorded).split(";")
            if part
        }
    )
    gate_text = (
        "No specification failed a prospectively specified estimation gate."
        if not failures
        else "Failed estimation gates, recorded rather than dropped: "
        + _escape_latex(", ".join(failures).replace("_", " "))
        + "."
    )
    if _interval_is_calibrated(dossier_dir) is not True:
        gate_text += (
            " In the status column the first entry is the estimation gate and the second "
            "the interval. The "
            "diagnostic in Appendix~\\\\ref{sec:validation}, which resamples fewer times than "
            "the reported intervals do, did not confirm nominal coverage."
        )

    return (
        f"{int(record['nobs'])} observations from {int(record['n_countries'])} countries over "
        f"{int(record['n_effective_years'])} effective years. The specification, the bias "
        "correction and the bootstrap are described in "
        "Section~\\\\ref{sec:dynamic-panel}. LSDVC is the bias-corrected estimator and is the "
        "substantive one. LSDV is shown beside it to give the size of the correction. Intervals "
        "are nominal percentile intervals for the multiplier, from "
        f"{int(record['replications_requested'])} moving-block replications at block length "
        f"{int(record['block_length'])}, of which {int(record['replications_completed'])} "
        "completed. The reverse-percentile interval on the primary specification is "
        f"{_reverse_interval(record)}, and the median replication gives "
        f"$\\\\hat{{\\\\Theta}}={_fmt_float(record['corrected_multiplier_bootstrap_median'])}$ "
        f"against a point estimate of {_fmt_float(record['corrected_multiplier'])}. The ratio is "
        f"finite in {_fmt_pct_fraction(record['finite_multiplier_share'])} of replications, with "
        f"$1-\\\\hat{{\\\\gamma}}$ ranging over "
        f"[{_fmt_float(record['one_minus_persistence_p2.5'])}, "
        f"{_fmt_float(record['one_minus_persistence_p97.5'])}] and never closer to zero than "
        f"{_fmt_float(record['one_minus_persistence_min_abs'])}. "
        f"{block_text}"
        "Driscoll--Kraay standard errors, a secondary diagnostic only: "
        f"$\\\\hat{{\\\\gamma}}$ {_fmt_float(record['driscoll_kraay_persistence_std_error'])}, "
        f"$\\\\sum\\\\hat{{\\\\beta}}_j$ "
        f"{_fmt_float(record['driscoll_kraay_driver_sum_std_error'])}, and "
        f"$\\\\hat{{\\\\Theta}}$ by the delta method "
        f"{_fmt_float(record['driscoll_kraay_multiplier_std_error'])}, at "
        f"{int(record['driscoll_kraay_lags'])} lags. "
        f"{gate_text}"
    )


def _values_file(
    core: pd.DataFrame,
    cross: pd.DataFrame,
    dossier_dir: Path,
) -> str:
    """Emit dossier numbers as LaTeX macros so prose cannot drift from the tables.

    A horizon-eight interval typed into the discussion survived an entire vintage after the
    table beside it had been regenerated at a higher replication count. Nothing tied the two
    together. These macros do.
    """
    lines = [
        "% AUTO-GENERATED. DO NOT EDIT.",
        "% Values quoted in prose. Defined here so they cannot drift from the tables.",
    ]

    def define(name: str, value: str) -> None:
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    def interval(low: Any, high: Any, digits: int = 3) -> str:
        return f"$[{_fmt_float(low, digits)},\\ {_fmt_float(high, digits)}]$"

    primary = core.loc[core["driver"] == "productivity_per_worker"]
    if not primary.empty:
        row = primary.iloc[0]
        define("valPrtTheta", _fmt_float(row["distributed_lag_cumulative"]))
        define("valPrtSe", _fmt_float(row["distributed_lag_std_error"]))
        define("valPrtCi", interval(row["distributed_lag_ci_low"], row["distributed_lag_ci_high"]))
        define("valPrtRegN", str(int(row["n_levels"]) - LOST_TO_LAGS))

    results = _verified_model_results(core, "productivity_per_worker")
    if results:
        points = {int(p["horizon"]): p for p in results.get("local_projections") or []}
        bands = {int(b["horizon"]): b for b in results.get("local_projection_bands") or []}
        longest = max(points) if points else None
        if longest is not None:
            define("valLpHorizon", str(longest))
            define("valLpHac", interval(points[longest]["lower_95"], points[longest]["upper_95"]))
            if longest in bands:
                define(
                    "valLpBootstrap",
                    interval(bands[longest]["lower_95"], bands[longest]["upper_95"]),
                )

    cross_primary = cross.loc[cross["driver"] == "productivity_per_worker"]
    if not cross_primary.empty:
        row = cross_primary.iloc[0]
        estimate = float(row["random_effect_estimate"])
        std_error = float(row["random_effect_std_error"])
        define("valReEstimate", _fmt_float(estimate))
        define("valReSe", _fmt_float(std_error))
        define("valReCi", interval(estimate - 1.96 * std_error, estimate + 1.96 * std_error))
        define("valMedianCountry", _fmt_float(row["median_cumulative_transmission"]))
        define("valISquared", _fmt_pct_fraction(float(row["i_squared_percent"]) / 100.0))
        if "q25_cumulative_transmission" in cross.columns:
            define("valIqrLow", _fmt_float(row["q25_cumulative_transmission"]))
        if "q75_cumulative_transmission" in cross.columns:
            define("valIqrHigh", _fmt_float(row["q75_cumulative_transmission"]))
        define("valCountryCount", str(int(row["n_countries"])))
        if "positive_country_share" in cross.columns:
            positive = round(float(row["positive_country_share"]) * int(row["n_countries"]))
            define("valPositiveCount", str(positive))
        estimates_path = Path(str(row.get("country_estimates_path") or ""))
        if not estimates_path.is_file():
            estimates_path = dossier_dir / estimates_path.name
        if estimates_path.is_file():
            column = pd.read_csv(estimates_path)["distributed_lag_cumulative"]
            define("valCountryMin", _fmt_float(column.min()))
            define("valCountryMax", _fmt_float(column.max()))

    hour_cross = cross.loc[cross["driver"] == "productivity"]
    if not hour_cross.empty:
        row = hour_cross.iloc[0]
        define("valHourMedian", _fmt_float(row["median_cumulative_transmission"]))
        define("valHourRe", _fmt_float(row["random_effect_estimate"]))
        summary = _verified_summary(cross, dossier_dir, "productivity_per_worker")
        if "tau_squared" in summary:
            define("valTauSquared", _fmt_float(summary["tau_squared"], 4))

    panel_path = dossier_dir / "dynamic_panel_summary.csv"
    if panel_path.is_file():
        panel = pd.read_csv(panel_path)
        for driver, prefix in (
            ("productivity_per_worker", "valPanelPrimary"),
            ("productivity", "valPanelHour"),
        ):
            for effects, suffix in (("country_and_year", "Year"), ("country", "Country")):
                matched = panel.loc[
                    (panel["driver"] == driver)
                    & (panel["fixed_effects"] == effects)
                    & (panel["role"].isin(["primary", "sensitivity_fixed_effects"]))
                ]
                if matched.empty:
                    continue
                record = matched.iloc[0]
                estimate = float(record["corrected_multiplier"])
                low = float(record["corrected_multiplier_ci_low"])
                high = float(record["corrected_multiplier_ci_high"])
                define(f"{prefix}{suffix}Theta", _fmt_float(estimate))
                define(f"{prefix}{suffix}Ci", interval(low, high))
                define(
                    f"{prefix}{suffix}Reverse",
                    interval(2.0 * estimate - high, 2.0 * estimate - low),
                )
                define(
                    f"{prefix}{suffix}Median",
                    _fmt_float(record["corrected_multiplier_bootstrap_median"]),
                )
                define(f"{prefix}{suffix}Obs", str(int(record["nobs"])))

    # Spans of the decomposition contributions. The claim they support is comparative, so the
    # spans are quoted rather than characterised.
    decomposition_path = dossier_dir / "decomposition_summary.csv"
    if decomposition_path.is_file():
        decomposition = pd.read_csv(decomposition_path)
        spans = {
            "valSpanOutput": "real_gdp_log_contribution",
            "valSpanEmployment": "employment_log_contribution",
            "valSpanWedge": "relative_price_log_contribution",
            "valSpanLabourShare": "labour_share_log_contribution",
        }
        for name, column in spans.items():
            if column in decomposition:
                values = decomposition[column].astype(float)
                define(name, _fmt_float(values.max() - values.min()))

    # Bias removed by the correction, across the simulated persistence grid.
    validation_path = dossier_dir / "dynamic_panel_validation.json"
    if validation_path.is_file():
        validation = _load_json_object(validation_path)
        removed = [
            float(entry["persistence_bias_removed"])
            for entry in validation.get("bias_study") or []
            if entry.get("persistence_bias_removed") is not None
        ]
        if removed:
            define("valBiasRemovedMin", _fmt_pct_fraction(min(removed)))
            define("valBiasRemovedMax", _fmt_pct_fraction(max(removed)))
        grid = [float(entry["true_persistence"]) for entry in validation.get("bias_study") or []]
        if grid:
            define("valBiasGammaLow", _fmt_float(min(grid), 1))
            define("valBiasGammaHigh", _fmt_float(max(grid), 1))

    # The post-hoc comparison of the two functionals. Nothing here revises a reported estimate;
    # these say how far apart the impact sum and the long-run response are.
    longrun_path = dossier_dir / "longrun_sensitivity.json"
    if longrun_path.is_file():
        payload = _load_json_object(longrun_path)
        per_worker = (payload.get("drivers") or {}).get("productivity_per_worker") or {}
        if per_worker:
            define("valLongRunMedian", _fmt_float(per_worker.get("median_long_run")))
            define("valImpactAboveOne", str(int(per_worker.get("n_impact_above_one", 0))))
            define("valLongRunAboveOne", str(int(per_worker.get("n_long_run_above_one", 0))))
            define("valFiellerUnbounded", str(int(per_worker.get("n_fieller_unbounded", 0))))
            countries = per_worker.get("countries") or []
            above = sorted(
                str(entry["country"]) for entry in countries if float(entry["long_run"]) > 1.0
            )
            define("valLongRunAboveOneNames", " and ".join(above) if above else "none")
            persistence = [float(entry["persistence"]) for entry in countries]
            if persistence:
                define("valPersistenceMin", _fmt_float(min(persistence)))
                define("valPersistenceMax", _fmt_float(max(persistence)))
            for entry in countries:
                if str(entry.get("country")) != "PRT":
                    continue
                define("valPrtLongRun", _fmt_float(entry["long_run"]))
                define("valPrtPersistence", _fmt_float(entry["persistence"]))
                define(
                    "valPrtLongRunFieller",
                    interval(entry["long_run_fieller_ci_low"], entry["long_run_fieller_ci_high"]),
                )
                define(
                    "valPrtLongRunDeltaCi",
                    interval(entry["long_run_delta_ci_low"], entry["long_run_delta_ci_high"]),
                )
    return "\n".join(lines) + "\n"


def _primary_results_text(
    core: pd.DataFrame, cross: pd.DataFrame, reliability: pd.DataFrame
) -> str:
    primary = core.loc[core["role"] == "primary"]
    if len(primary) != 1:
        raise ValueError("Exactly one primary driver row is required in core_estimates.csv.")
    row = primary.iloc[0]
    driver = _driver_label(str(row["driver"]))
    estimate = _fmt_float(row["distributed_lag_cumulative"])
    se = _fmt_float(row["distributed_lag_std_error"])
    low = _fmt_float(row["distributed_lag_ci_low"])
    high = _fmt_float(row["distributed_lag_ci_high"])
    p_value = _fmt_float(row["distributed_lag_p_value"])
    wage_growth = _fmt_pct_fraction(row.get("annualized_wage_growth"))
    driver_growth = _fmt_pct_fraction(row.get("annualized_driver_growth"))

    eligible_models = (
        reliability.loc[
            (reliability["driver"] == row["driver"])
            & reliability["claim_eligible"].map(_bool_value),
            "model",
        ]
        .astype(str)
        .tolist()
    )
    ineligible_models = (
        reliability.loc[
            (reliability["driver"] == row["driver"])
            & ~reliability["claim_eligible"].map(_bool_value),
            "model",
        ]
        .astype(str)
        .tolist()
    )

    cross_primary = cross.loc[cross["driver"] == row["driver"]]
    cross_sentence = "Cross-country context was unavailable."
    if len(cross_primary) == 1:
        c = cross_primary.iloc[0]
        cross_sentence = (
            f"Across {int(c['n_countries'])} countries, the median country-specific coefficient was "
            f"{_fmt_float(c['median_cumulative_transmission'])}. The secondary random-effects summary was "
            f"{_fmt_float(c['random_effect_estimate'])} with $I^2={_fmt_float(c['i_squared_percent'], 1)}\\%$."
        )

    # The state-space model carries no eligibility verdict, so it appears in neither list.
    eligible_text = (
        ", ".join(
            _escape_latex(MODEL_LABELS.get(item, item.replace("_", " ")).lower())
            for item in eligible_models
            if item != "state_space_latest"
        )
        or "none"
    )
    ineligible_text = (
        ", ".join(
            _escape_latex(MODEL_LABELS.get(item, item.replace("_", " ")).lower())
            for item in ineligible_models
            if item != "state_space_latest"
        )
        or "none"
    )
    return f"""% AUTO-GENERATED. DO NOT EDIT.
\\subsection{{Pre-specified primary result}}
The primary specification uses {_escape_latex(driver)}. Over {int(row["start_year"])}--{int(row["end_year"])}, annualised real wage growth was {wage_growth} and annualised driver growth was {driver_growth}. The pre-specified cumulative distributed-lag estimate was $\\hat{{\\Theta}}={estimate}$ (HAC SE {se}; 95\\% CI [{low}, {high}]; $p={p_value}$). This is a reduced-form association and is not interpreted causally.

{cross_sentence}

Supporting models eligible for substantive interpretation: {eligible_text}. Supporting models not eligible under the pre-specified rules: {ineligible_text}. The state-space slope is governed by no such rule and is reported as inconclusive. Estimates that are not eligible remain reported in Table~\\ref{{tab:reliability-gates}} rather than being omitted.
"""


def _markdown_summary(core: pd.DataFrame, cross: pd.DataFrame, reliability: pd.DataFrame) -> str:
    primary = core.loc[core["role"] == "primary"].iloc[0]
    lines = [
        "# Paper-facing results packet",
        "",
        "This file is generated from a hash-verified publication dossier. It contains no manually entered empirical coefficient.",
        "",
        "## Primary result",
        "",
        f"- Driver: **{_driver_label(str(primary['driver']))}**",
        f"- Sample: {int(primary['start_year'])}–{int(primary['end_year'])}",
        f"- Cumulative distributed-lag estimate: **{_fmt_float(primary['distributed_lag_cumulative'])}**",
        f"- HAC SE: {_fmt_float(primary['distributed_lag_std_error'])}",
        f"- 95% CI: [{_fmt_float(primary['distributed_lag_ci_low'])}, {_fmt_float(primary['distributed_lag_ci_high'])}]",
        f"- p-value: {_fmt_float(primary['distributed_lag_p_value'])}",
        "- Causal interpretation: **not authorized**",
        "",
        "## Reliability gates",
        "",
    ]
    for _, row in reliability.loc[reliability["driver"] == primary["driver"]].iterrows():
        status = "eligible" if _bool_value(row["claim_eligible"]) else "not eligible"
        lines.append(f"- `{row['model']}`: **{status}** — {row['reason']}")
    cross_primary = cross.loc[cross["driver"] == primary["driver"]]
    if len(cross_primary) == 1:
        row = cross_primary.iloc[0]
        lines.extend(
            [
                "",
                "## Cross-country context",
                "",
                f"- Countries: {int(row['n_countries'])}",
                f"- Median country-specific coefficient: {_fmt_float(row['median_cumulative_transmission'])}",
                f"- Random-effects summary: {_fmt_float(row['random_effect_estimate'])}",
                f"- I²: {_fmt_float(row['i_squared_percent'], 1)}%",
            ]
        )
    return "\n".join(lines) + "\n"


def _primary_prose(core: pd.DataFrame) -> str:
    """The reading instructions and the ratio caveat for the primary estimates table."""
    return (
        "In Table~\\ref{tab:core-estimates}, \\emph{Levels} is the length of the input series "
        "and \\emph{Reg.\\ $N$} the regression sample after differencing and two driver lags."
        + _multiplier_note(core)
    )


def _panel_prose(frame: pd.DataFrame, dossier_dir: Path) -> str:
    """Diagnostics for the dynamic panel that appear in no table column."""
    primary = frame.loc[
        (frame["role"] == "primary") & (frame["driver"] == "productivity_per_worker")
    ]
    if primary.empty:
        primary = frame.loc[frame["role"] == "primary"]
    record = primary.iloc[0]

    sensitivity = frame.loc[
        (frame["role"] == "sensitivity_block_length") & (frame["driver"] == str(record["driver"]))
    ].sort_values("block_length")
    block_parts = [
        "a block length of {} gives $\\hat{{\\Theta}}={}$ with $[{}, {}]$".format(
            int(row["block_length"]),
            _fmt_float(row["corrected_multiplier"]),
            _fmt_float(row["corrected_multiplier_ci_low"]),
            _fmt_float(row["corrected_multiplier_ci_high"]),
        )
        for _, row in sensitivity.iterrows()
    ]
    blocks = (
        "The prospectively specified block-length checks move the interval very little: "
        + " and ".join(block_parts)
        + ". "
        if block_parts
        else ""
    )

    failures = sorted(
        {
            part
            for recorded in frame["gate_failures"].fillna("")
            for part in str(recorded).split(";")
            if part
        }
    )
    gates = (
        "No specification failed a prospectively specified estimation gate. "
        if not failures
        else "Estimation gates that failed, recorded rather than dropped: "
        + _escape_latex(", ".join(failures).replace("_", " "))
        + ". "
    )
    if _interval_is_calibrated(dossier_dir) is not True:
        gates += (
            "In the status column the first entry is the estimation gate and the second the "
            "interval: here the estimation gates passed and the coverage diagnostic did "
            "not confirm the nominal level. "
        )

    return (
        "Three diagnostics sit behind Table~\\ref{tab:dynamic-panel} without appearing in it. "
        "The denominator of the multiplier stays well away from zero: across replications "
        f"$1-\\hat{{\\gamma}}$ ranges over "
        f"[{_fmt_float(record['one_minus_persistence_p2.5'])}, "
        f"{_fmt_float(record['one_minus_persistence_p97.5'])}], never coming closer to zero than "
        f"{_fmt_float(record['one_minus_persistence_min_abs'])}, and the ratio is finite in "
        f"{_fmt_pct_fraction(record['finite_multiplier_share'])} of them. The median replication "
        f"gives $\\hat{{\\Theta}}="
        f"{_fmt_float(record['corrected_multiplier_bootstrap_median'])}$ against a point estimate "
        f"of {_fmt_float(record['corrected_multiplier'])}, and reflecting that displacement gives "
        f"a reverse-percentile interval of {_reverse_interval(record)}. "
        + blocks
        + "Driscoll--Kraay standard errors, reported as a secondary diagnostic only, are "
        f"{_fmt_float(record['driscoll_kraay_persistence_std_error'])} for $\\hat{{\\gamma}}$, "
        f"{_fmt_float(record['driscoll_kraay_driver_sum_std_error'])} for "
        f"$\\sum\\hat{{\\beta}}_j$ and "
        f"{_fmt_float(record['driscoll_kraay_multiplier_std_error'])} for $\\hat{{\\Theta}}$ "
        f"by the delta method, at {int(record['driscoll_kraay_lags'])} lags. " + gates
    )


def _validation_prose(dossier_dir: Path) -> str:
    """Calibration and solver settings for the Monte Carlo study."""
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return ""
    payload = _load_json_object(path)
    design = payload.get("design") or {}
    calibration = payload.get("calibration") or {}
    if not design:
        return ""
    beta = ", ".join(_fmt_float(value) for value in design.get("beta", []))
    return (
        "The simulated panels carry the dimensions of the estimation sample: "
        f"{int(design.get('n_countries', 0))} countries, "
        f"{int(design.get('n_growth_years', 0))} annual growth observations, one country a year "
        "short, and country and year effects. Driver growth has mean "
        f"{_fmt_float(calibration.get('driver_mean'), 4)} and within-year standard deviation "
        f"{_fmt_float(calibration.get('driver_sd'), 4)}, with a common annual component of "
        f"standard deviation {_fmt_float(calibration.get('driver_common_sd'), 4)}. The errors "
        f"have standard deviation {_fmt_float(calibration.get('error_sd'), 4)}. Country effects "
        f"have standard deviation {_fmt_float(calibration.get('country_effect_sd'), 4)} and year "
        f"effects {_fmt_float(calibration.get('year_effect_sd'), 4)}."
        f" Driver coefficients are held at $({beta})$, and the correction "
        f"uses {int(design.get('bias_correction_draws_bias_study', 0))} simulation draws and at "
        f"most {int(design.get('bias_correction_max_iterations', 0))} iterations to a tolerance "
        "of $10^{-7}$, and every draw converged."
    )


def _validation_table_prose(dossier_dir: Path) -> str:
    """What the columns of the bias and coverage tables mean."""
    path = dossier_dir / "dynamic_panel_validation.json"
    if not path.is_file():
        return ""
    payload = _load_json_object(path)
    coverage = payload.get("coverage_study") or []
    if not payload.get("design"):
        return ""
    reps = int(coverage[0].get("bootstrap_replications", 0)) if coverage else 0
    return (
        "``Removed'' in Table~\\ref{tab:validation-bias} is the proportional reduction in "
        "\\emph{absolute} bias, $1-|\\text{LSDVC bias}|/|\\text{LSDV bias}|$. Taking absolute "
        "values matters: at $\\gamma=0.50$ the residual bias has the opposite sign to the "
        "original, so a ratio of the signed quantities would exceed one, which is why both signed "
        "biases are printed beside it. In Table~\\ref{tab:validation-coverage} each draw runs the "
        f"whole procedure at {reps} moving-block replications, the reverse-percentile interval is "
        "$[2\\hat{\\Theta}-q_{0.975},\\ 2\\hat{\\Theta}-q_{0.025}]$, and reflection "
        "preserves interval length exactly, so both interval types share the width column. "
        "``Displacement'' is the mean gap between the median replication and the point estimate, "
        "and the bracketed figures are exact Clopper--Pearson intervals for the coverage estimate "
        "itself."
    )


def build_paper_packet(*, dossier_dir: Path, paper_dir: Path) -> PaperPacket:
    """Build LaTeX/Markdown fragments using only a verified publication dossier."""
    dossier_manifest = verify_dossier(dossier_dir)
    generated = paper_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)

    core = pd.read_csv(dossier_dir / "core_estimates.csv")
    reliability = pd.read_csv(dossier_dir / "reliability_gates.csv")
    cross = pd.read_csv(dossier_dir / "cross_country_summary.csv")

    results_primary = _write(
        generated / "results_primary.tex", _primary_results_text(core, cross, reliability)
    )
    core_table = _write(generated / "table_core_estimates.tex", _core_table(core))
    reliability_table = _write(
        generated / "table_reliability.tex", _reliability_table(reliability, core)
    )
    cross_table = _write(
        generated / "table_cross_country.tex", _cross_country_table(cross, dossier_dir)
    )
    # Optional, like the decomposition table: a dossier need not record a path to the
    # country-level estimates. When it does, the table is written and bound into the
    # manifest; when it does not, main.tex falls through its IfFileExists guard.
    optional_paths: list[Path] = []
    country_table = _country_estimates_table(cross, dossier_dir)
    if country_table is not None:
        optional_paths.append(_write(generated / "table_country_estimates.tex", country_table))

    projection_table = _local_projection_table(core)
    if projection_table is not None:
        optional_paths.append(_write(generated / "table_local_projections.tex", projection_table))

    forest = _forest_plot(cross, dossier_dir, generated / "figure_forest.pdf")
    if forest is not None:
        optional_paths.append(forest)

    sources = _source_table(Path("config/data_sources.yml"))
    if sources is not None:
        optional_paths.append(_write(generated / "table_sources.tex", sources))

    breaks = _break_table(core)
    if breaks is not None:
        optional_paths.append(_write(generated / "table_breaks.tex", breaks))

    dynamic_panel = _dynamic_panel_table(dossier_dir)
    if dynamic_panel is not None:
        optional_paths.append(_write(generated / "table_dynamic_panel.tex", dynamic_panel))

    for name, body in _validation_tables(dossier_dir):
        optional_paths.append(_write(generated / name, body))
    for name, body in _design_tables(dossier_dir):
        optional_paths.append(_write(generated / name, body))
    benchmark_table = _benchmark_coverage_table(dossier_dir)
    if benchmark_table is not None:
        optional_paths.append(_write(generated / benchmark_table[0], benchmark_table[1]))
    benchmark_prose = _benchmark_prose(dossier_dir)
    if benchmark_prose:
        optional_paths.append(_write(generated / "prose_benchmark.tex", benchmark_prose))

    # Explanatory material goes into the manuscript as ordinary prose, never under a float.
    optional_paths.append(_write(generated / "prose_primary.tex", _primary_prose(core)))
    panel_path = dossier_dir / "dynamic_panel_summary.csv"
    if panel_path.is_file():
        optional_paths.append(
            _write(
                generated / "prose_panel.tex",
                _panel_prose(pd.read_csv(panel_path), dossier_dir),
            )
        )
    validation_prose = _validation_prose(dossier_dir)
    if validation_prose:
        optional_paths.append(_write(generated / "prose_validation.tex", validation_prose))
    validation_table_prose = _validation_table_prose(dossier_dir)
    if validation_table_prose:
        optional_paths.append(
            _write(generated / "prose_validation_tables.tex", validation_table_prose)
        )

    optional_paths.append(_write(generated / "values.tex", _values_file(core, cross, dossier_dir)))

    markdown_summary = _write(
        generated / "results_summary.md", _markdown_summary(core, cross, reliability)
    )

    decomposition_table: Path | None = None
    decomposition_path = dossier_dir / "decomposition_summary.csv"
    if decomposition_path.is_file():
        decomposition = pd.read_csv(decomposition_path)
        primary_country = str(dossier_manifest.get("primary_country") or "PRT")
        main_rows = decomposition.loc[decomposition["country"] == primary_country]
        decomposition_table = _write(
            generated / "table_decomposition.tex",
            _decomposition_table(main_rows if not main_rows.empty else decomposition),
        )
        # The full set goes to an appendix, so the coverage claim can be checked.
        if len(decomposition) > 1:
            appendix = _decomposition_appendix(decomposition)
            if appendix:
                optional_paths.append(
                    _write(generated / "table_decomposition_appendix.tex", appendix)
                )

    generated_paths = [
        results_primary,
        core_table,
        reliability_table,
        cross_table,
        markdown_summary,
    ]
    if decomposition_table is not None:
        generated_paths.append(decomposition_table)
    # Every optional artefact is bound into the manifest too, so nothing published is unhashed.
    generated_paths.extend(optional_paths)

    manifest_payload = {
        "schema_version": 1,
        "purpose": "paper_formatting_only",
        "causal_claims_authorized": False,
        "dossier_manifest_file": "publication_manifest.json",
        "dossier_manifest_sha256": sha256_file(dossier_dir / "publication_manifest.json"),
        "specification_lock_label": dossier_manifest.get("specification_lock_label"),
        "primary_driver": dossier_manifest.get("primary_driver"),
        "primary_estimand": dossier_manifest.get("primary_estimand"),
        "inputs": {
            path.name: sha256_file(path) for path in sorted(dossier_dir.iterdir()) if path.is_file()
        },
        "outputs": {f"generated/{path.name}": sha256_file(path) for path in generated_paths},
    }
    packet_manifest = generated / "paper_packet_manifest.json"
    _write(packet_manifest, json.dumps(manifest_payload, indent=2, sort_keys=True))
    return PaperPacket(
        generated_dir=generated,
        results_primary=results_primary,
        core_table=core_table,
        reliability_table=reliability_table,
        cross_country_table=cross_table,
        decomposition_table=decomposition_table,
        markdown_summary=markdown_summary,
        manifest=packet_manifest,
    )


def audit_paper_sources(*, paper_dir: Path, generated_manifest: Path) -> None:
    """Fail when empirical tables are manually embedded or generated hashes drift."""
    manifest = _load_json_object(generated_manifest)
    if manifest.get("purpose") != "paper_formatting_only":
        raise ValueError("Invalid paper-packet manifest purpose.")
    if manifest.get("causal_claims_authorized") is not False:
        raise ValueError("Paper packet must explicitly disable causal claims.")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("Paper-packet manifest must contain outputs.")
    for raw_path, expected in outputs.items():
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            raise ValueError("Paper-packet output entries must be path -> SHA-256 strings.")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ValueError("Paper-packet output paths must be portable relative paths.")
        path = paper_dir / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"Generated paper fragment hash mismatch: {path.name}")

    generated_dir = paper_dir / "generated"
    manual_sources = [
        path
        for path in paper_dir.rglob("*.tex")
        if path.is_file() and generated_dir not in path.parents
    ]
    empirical_markers = ("\\hat{\\Theta}=", "HAC SE", "95\\% CI", "$p=")
    violations: list[str] = []
    for path in manual_sources:
        source_text = path.read_text(encoding="utf-8")
        if any(pattern.search(source_text) for pattern in MANUAL_TABLE_PATTERNS):
            violations.append(f"manual_table:{path}")
        if any(marker in source_text for marker in empirical_markers):
            violations.append(f"manual_empirical_value:{path}")
    if violations:
        raise ValueError(
            "Manual empirical table environments are forbidden outside paper/generated: "
            + ", ".join(violations)
        )

    main = paper_dir / "main.tex"
    if not main.is_file():
        raise FileNotFoundError(main)
    text = main.read_text(encoding="utf-8")
    for name in REQUIRED_GENERATED_FILES:
        generated_path = generated_dir / name
        if not generated_path.is_file():
            raise FileNotFoundError(generated_path)
    for name in (
        "results_primary.tex",
        "table_core_estimates.tex",
        "table_reliability.tex",
        "table_cross_country.tex",
    ):
        if f"generated/{name}" not in text:
            raise ValueError(f"paper/main.tex does not include generated/{name}")


OVERFULL_PATTERN = re.compile(r"Overfull \\hbox \(([0-9.]+)pt too wide\)")


def preflight_pdf(paper_dir: Path, *, tolerance_pt: float = 1.0) -> int:
    """Fail when the compiled manuscript has content running past the margin.

    A successful pdflatex exit code says nothing about layout: TeX reports overfull boxes as
    warnings and still writes a PDF with text running off the page. Checking the exit status
    alone let a manuscript through with a table 262pt past the margin, so the log is the thing
    that must be read.
    """
    log_path = paper_dir / "main.log"
    if not log_path.is_file():
        raise FileNotFoundError(
            f"{log_path} not found; compile the manuscript before running preflight."
        )
    text = log_path.read_text(encoding="utf-8", errors="replace")

    offenders: list[tuple[float, str]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = OVERFULL_PATTERN.search(line)
        if not match:
            continue
        width = float(match.group(1))
        if width <= tolerance_pt:
            continue
        context = next(
            (
                lines[offset].strip()
                for offset in range(index + 1, min(index + 4, len(lines)))
                if lines[offset].strip()
            ),
            "",
        )
        offenders.append((width, f"{line.strip()} | {context[:90]}"))

    # Overfull boxes were only part of what a broken manuscript looks like. Cross-references can
    # print as "??", and a control sequence mangled at generation time can reach the page as
    # literal text. Neither changes the exit code, and both survived a check that looked only at
    # box widths.
    failures: list[str] = []
    for line in lines:
        if line.startswith("LaTeX Warning: Reference"):
            failures.append(line.strip())
    if not failures and "There were undefined references" in text:
        failures.append("LaTeX reported undefined references.")
    if "multiply-defined labels" in text:
        failures.append("Multiply-defined labels: a reference may resolve to the wrong float.")

    # A backslash lost inside a Python string becomes a control character: "\\appendix"
    # turns into BEL plus "ppendix", and "\\ref" into a carriage return plus "ef". TeX
    # typesets both as stray text and warns about neither. Sources here are LF-only, so a
    # carriage return is not a line ending: it is the signature of the second case.
    #
    # Matching a command's tail alone would also match the intact command, so each pattern
    # requires that the characters which should precede it are absent. Every source is
    # scanned, not only the generated fragments: the manuscript is mangled the same way.
    damaged = (
        (re.compile(r"(?<!\\r)ef\{(?:tab|fig|sec):"), "ref"),
        (re.compile(r"(?<!\\t)extbf\{"), "textbf"),
        (re.compile(r"(?<!\\t)extit\{"), "textit"),
    )
    for source in sorted(paper_dir.rglob("*.tex")):
        raw = source.read_bytes()
        name = source.relative_to(paper_dir)
        without_line_endings = raw.replace(b"\r\n", b"\n")
        stray = {byte for byte in without_line_endings if byte < 32 and byte not in (9, 10)}
        if stray:
            names = ", ".join(f"0x{byte:02x}" for byte in sorted(stray))
            failures.append(
                f"{name}: control character(s) {names} in the source. A backslash was lost "
                "from a command, leaving its escape code behind."
            )
        body = raw.decode("utf-8", errors="replace")
        for pattern, command in damaged:
            if pattern.search(body):
                failures.append(
                    f"{name}: a backslash was lost from a {command} command, so it reaches "
                    "the page as literal text."
                )

    if failures:
        print(f"Preflight FAILED: {len(failures)} reference or markup problem(s).")
        for failure in failures:
            print(f"  {failure}")
        if offenders:
            print()

    if not offenders:
        if failures:
            return 1
        print("Preflight passed: no overfull boxes, undefined references or damaged commands.")
        return 0

    offenders.sort(reverse=True)
    print(f"Preflight FAILED: {len(offenders)} overfull box(es) exceed {tolerance_pt}pt.")
    for width, detail in offenders:
        print(f"  {width:8.1f}pt  {detail}")
    print(
        "\nContent running past the margin is clipped in the PDF. Fix the source rather than "
        "raising the tolerance."
    )
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build paper fragments from a publication dossier.")
    build.add_argument("--dossier", type=Path, required=True)
    build.add_argument("--paper-dir", type=Path, default=Path("paper"))

    audit = subparsers.add_parser(
        "audit", help="Audit generated paper fragments and manual-source rules."
    )
    audit.add_argument("--paper-dir", type=Path, default=Path("paper"))
    audit.add_argument(
        "--manifest",
        type=Path,
        default=Path("paper/generated/paper_packet_manifest.json"),
    )

    preflight = subparsers.add_parser(
        "preflight", help="Fail if the compiled manuscript runs past the margin."
    )
    preflight.add_argument("--paper-dir", type=Path, default=Path("paper"))
    preflight.add_argument("--tolerance-pt", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        packet = build_paper_packet(dossier_dir=args.dossier, paper_dir=args.paper_dir)
        print(f"Paper packet written to {packet.generated_dir}; manifest={packet.manifest}")
        return 0
    if args.command == "preflight":
        return preflight_pdf(args.paper_dir, tolerance_pt=args.tolerance_pt)
    audit_paper_sources(paper_dir=args.paper_dir, generated_manifest=args.manifest)
    print(f"Paper packet audit passed: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
