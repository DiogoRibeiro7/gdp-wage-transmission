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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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
    note: str,
    size: str = "footnotesize",
) -> str:
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
\\begin{{minipage}}{{0.96\\linewidth}}
\\footnotesize {note}
\\end{{minipage}}
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
        note=(
            "The primary estimand is the cumulative distributed-lag coefficient. "
            "GDP per person employed is the pre-specified primary driver; GDP per hour is "
            "secondary. Levels is the input series length; Reg.\\ $N$ is the regression sample "
            "after differencing and two driver lags. "
            "These are reduced-form associations, not causal effects." + _multiplier_note(core)
        ),
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
        caption="Supporting models, their estimates, and their pre-specified reliability gates.",
        label="tab:reliability-gates",
        columns="p{2.3cm}p{2.2cm}lp{1.5cm}p{3.6cm}",
        header="Driver & Model & Estimate & Claim status & Gate result",
        rows=rows,
        note=(
            "A supporting estimate may be discussed substantively only when its pre-specified "
            "reliability gate is eligible. Non-eligible estimates are shown rather than dropped, "
            "so a reader can see what was gated and why. State-space entries report the latest "
            "slope with its standard error; asymmetry reports the positive and negative "
            "cumulative responses; breaks report the selected years."
        ),
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
        note=(
            "Each row is the same pre-specified specification estimated separately on one "
            r"country. Levels is the input series length; Reg.\ $N$ is the regression sample, "
            r"which loses one observation to differencing and two to the driver lags. EG $p$ is "
            r"the Engle--Granger cointegration p-value on log levels, and the final column "
            r"reports whether it supports cointegration at 5\%. "
            "These estimates are the primary cross-country object; the summary in "
            "Table~\\ref{tab:cross-country} is secondary and should be read together with the "
            "heterogeneity statistic. Intervals are normal approximations from the HAC standard "
            "error. Country estimates over a common period are not independent, since countries "
            "share global and European shocks, so a summary treating them as independent may "
            "understate uncertainty."
        ),
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
        note=(
            "Cumulative log-wage response at each horizon, for both drivers. Horizons marked "
            "$\\dagger$ fall below the pre-specified minimum effective sample and are "
            "exploratory. The bootstrap interval is a circular moving-block percentile interval "
            "that resamples the joint growth pairs; it is wider than the HAC interval at longer "
            "horizons because overlapping windows leave few effective observations there. "
            "These are dynamic associations, not impulse responses to an identified shock."
        ),
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
    summary_se = float(row["random_effect_std_error"])

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
    axes.axvspan(
        summary - 1.96 * summary_se, summary + 1.96 * summary_se, color="#3060a0", alpha=0.13
    )
    axes.axvline(summary, color="#3060a0", linewidth=1.4)

    axes.set_yticks(list(positions))
    axes.set_yticklabels(labels)
    axes.set_ylim(-0.8, len(values) - 0.2)
    axes.set_xlabel("Cumulative transmission of productivity growth into real wages")
    axes.set_title("Country-specific estimates and random-effects summary", fontsize=10)
    axes.text(
        summary,
        len(values) - 0.55,
        f"  RE {summary:.3f}",
        color="#3060a0",
        fontsize=8,
        va="center",
    )
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight")
    plt.close(figure)
    return output


def _cross_country_table(cross: pd.DataFrame) -> str:
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
        rows.append(
            "{} & {} & {} & {} & {} & {}\\% \\\\".format(
                _escape_latex(_driver_label(str(row["driver"]))),
                int(row["n_countries"]),
                _fmt_float(row["median_cumulative_transmission"]),
                _fmt_float(row["random_effect_estimate"]),
                _fmt_float(row["random_effect_std_error"]),
                _fmt_float(row["i_squared_percent"], 1),
            )
        )
    return _table_wrapper(
        caption="Cross-country context for cumulative wage transmission.",
        label="tab:cross-country",
        columns="lrrrrr",
        header="Driver & Countries & Median & RE estimate & RE SE & $I^2$",
        rows=rows,
        note=(
            "Country-specific estimates are the primary cross-country object. "
            "The random-effects estimate is a secondary summary and should be read together with heterogeneity."
        ),
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
        note=(
            "The decomposition is an exact accounting identity: the components sum to the observed "
            "change, and the residual reports the closure error. Components describe where wage "
            "growth is accounted for; they are not causal effects. A negative employee "
            "contribution means a growing wage bill divided among more people."
        ),
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

    period_note = (
        f"All countries span {int(frame['start_year'].iloc[0])}--"
        f"{int(frame['end_year'].iloc[0])}, so the cumulative changes are directly comparable."
        if common_period
        else (
            "Periods differ across countries, so the cumulative changes are not comparable and an "
            "annualised column is reported alongside them."
        )
    )
    return _table_wrapper(
        caption="Accounting decomposition by country (log points).",
        label="tab:decomposition-appendix",
        columns=columns,
        header=" & ".join(header),
        rows=rows,
        note=(
            f"{period_note} Each row is an exact accounting identity: the four components sum to "
            "the observed change and the residual reports closure error. The United Kingdom is "
            "absent because Eurostat returns no national-accounts observations for it over this "
            "range. Components describe where wage growth is accounted for, not what caused it."
        ),
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
    "labour_productivity_and_ulc": "Robustness: independent productivity concepts",
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
        rows.append(
            "OECD & {} & {} & {} \\\\".format(
                _escape_latex(str(spec["flow_ref"])),
                _escape_latex(str(spec.get("measure", "--"))),
                _escape_latex(SOURCE_PURPOSES.get(name, name.replace("_", " "))),
            )
        )
    for name, spec in (config.get("eurostat") or {}).items():
        if not isinstance(spec, dict) or "dataset" not in spec:
            continue
        filters = spec.get("filters") or {}
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
        columns="lp{3.9cm}p{3.4cm}p{3.9cm}",
        header="Provider & Dataset or dataflow & Selection & Use",
        rows=rows,
        note=(
            "Generated from the configuration the download layer uses, so the identifiers cannot "
            "drift from what was retrieved. Every series is requested for the thirteen configured "
            "countries over 1995--2025 at annual frequency; the country list and window are the "
            "same for all sources and are therefore not repeated per row. Each extract is stored "
            "unchanged with its query URL, "
            "retrieval timestamp and SHA-256 digest. A response carrying more than one unit or "
            "price base is rejected rather than aggregated."
        ),
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
        note=(
            "The two columns on the left come from different procedures. BIC segmentation selects "
            "a number of regimes and always returns a partition, so it cannot indicate the absence "
            "of a break. The sup-$F$ statistic is the largest Chow $F$ over candidate dates after "
            "trimming 15\\% from each end, with a $p$-value from a Rademacher wild bootstrap that "
            "repeats the whole date search on each replication, so it already accounts for the "
            "search. The date interval is the percentile interval of the bootstrap arg-max. "
            "Minimum segment is the shortest regime the segmentation produced, against a "
            "pre-specified threshold of ten observations, which is why the gate is closed for both "
            "drivers."
        ),
    )


_FIXED_EFFECT_LABEL = {
    "country_and_year": "Country + year",
    "country": "Country only",
}

_ESTIMATOR_LABEL = {"lsdv": "LSDV", "corrected": "LSDVC"}


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
                gate = "eligible" if _bool_value(record["claim_eligible"]) else "not eligible"
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
            "$\\Theta_{\\mathrm{panel}}=(\\sum_j\\hat{\\beta}_j)/(1-\\hat{\\gamma})$."
        ),
        label="tab:dynamic-panel",
        columns="p{1.95cm}p{1.5cm}lrrrrrll",
        header=(
            r"Driver & Fixed effects & Est. & $N$ & Obs. & $\hat{\gamma}$ & "
            r"$\sum\hat{\beta}_j$ & $\hat{\Theta}$ & Bootstrap 95\% CI & Gate"
        ),
        rows=rows,
        note=_dynamic_panel_note(frame),
        size="scriptsize",
    )


def _dynamic_panel_note(frame: pd.DataFrame) -> str:
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
        "Frozen block-length sensitivities on the primary driver: " + "; ".join(block_parts) + ". "
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
        "No specification failed a pre-specified gate."
        if not failures
        else "Failed gates, recorded rather than dropped: "
        + _escape_latex(", ".join(failures).replace("_", " "))
        + "."
    )

    return (
        "Estimated on the same dynamic structure as the country models, "
        "$\\Delta\\log w_{it}=\\alpha_i+\\lambda_t+\\sum_{j=0}^{2}\\beta_j"
        "\\Delta\\log p_{i,t-j}+\\gamma\\Delta\\log w_{i,t-1}+u_{it}$, so the panel "
        "estimand is the same cumulative multiplier and not a contemporaneous slope. Two driver "
        "lags and one dependent lag cost three observations per country, which is why "
        f"{int(record['nobs'])} rows come from "
        f"{int(record['n_countries'])} countries and "
        f"{int(record['n_effective_years'])} effective years. The two drivers are estimated "
        "separately and never pooled. "
        "LSDVC is bias-corrected LSDV; LSDV is reported only to show the size of the correction, "
        "and only the corrected estimator is substantive. The correction is simulation-based "
        "rather than the analytical Kiviet--Bruno expansion, which assumes strictly exogenous "
        "regressors with individual effects only and does not accommodate the year effects the "
        "primary specification carries. "
        "The bias correction addresses dynamic fixed-effects bias. It does not solve "
        "contemporaneous endogeneity between productivity and wages. The coefficient remains a "
        "reduced-form conditional association. "
        "Intervals are percentile intervals for the nonlinear multiplier itself, from a circular "
        "moving-block bootstrap that resamples the complete "
        f"{int(record['n_countries'])}-country cross-section jointly with block length "
        f"{int(record['block_length'])}: "
        f"{int(record['replications_requested'])} replications requested and "
        f"{int(record['replications_completed'])} completed, the corrected model re-estimated in "
        "every one of them, lags rebuilt after block concatenation, and the short country's "
        "missing endpoint preserved. "
        "Gluing blocks breaks the dynamic relation at each boundary, so a replication's "
        "persistence is attenuated: the median replication gives "
        f"$\\hat{{\\Theta}}={_fmt_float(record['corrected_multiplier_bootstrap_median'])}$ "
        f"against a point estimate of {_fmt_float(record['corrected_multiplier'])}, and that gap "
        "is a property of the resampling scheme, not additional evidence. "
        "The denominator is well away from zero throughout: "
        f"$1-\\hat{{\\gamma}}$ has a bootstrap median of "
        f"{_fmt_float(record['one_minus_persistence_p50'])}, a 95\\% range of "
        f"[{_fmt_float(record['one_minus_persistence_p2.5'])}, "
        f"{_fmt_float(record['one_minus_persistence_p97.5'])}], and a minimum absolute value of "
        f"{_fmt_float(record['one_minus_persistence_min_abs'])} across replications, so the ratio "
        f"is finite in {_fmt_pct_fraction(record['finite_multiplier_share'])} of them. "
        f"{block_text}"
        "Driscoll--Kraay standard errors are reported as a secondary diagnostic only "
        f"($\\hat{{\\gamma}}$: {_fmt_float(record['driscoll_kraay_persistence_std_error'])}; "
        f"$\\sum\\hat{{\\beta}}_j$: "
        f"{_fmt_float(record['driscoll_kraay_driver_sum_std_error'])}; "
        f"$\\hat{{\\Theta}}$ by the delta method: "
        f"{_fmt_float(record['driscoll_kraay_multiplier_std_error'])}, "
        f"{int(record['driscoll_kraay_lags'])} lags). Their justification is asymptotic in the "
        f"time dimension, and {int(record['n_effective_years'])} effective years is "
        f"not enough for them to replace the bootstrap. {gate_text}"
    )


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
            f"{_fmt_float(c['median_cumulative_transmission'])}; the secondary random-effects summary was "
            f"{_fmt_float(c['random_effect_estimate'])} with $I^2={_fmt_float(c['i_squared_percent'], 1)}\\%$."
        )

    eligible_text = (
        ", ".join(
            _escape_latex(MODEL_LABELS.get(item, item.replace("_", " ")).lower())
            for item in eligible_models
        )
        or "none"
    )
    ineligible_text = (
        ", ".join(
            _escape_latex(MODEL_LABELS.get(item, item.replace("_", " ")).lower())
            for item in ineligible_models
        )
        or "none"
    )
    return f"""% AUTO-GENERATED. DO NOT EDIT.
\\subsection{{Pre-specified primary result}}
The primary specification uses {_escape_latex(driver)}. Over {int(row["start_year"])}--{int(row["end_year"])}, annualised real wage growth was {wage_growth} and annualised driver growth was {driver_growth}. The pre-specified cumulative distributed-lag estimate was $\\hat{{\\Theta}}={estimate}$ (HAC SE {se}; 95\\% CI [{low}, {high}]; $p={p_value}$). This is a reduced-form association and is not interpreted causally.

{cross_sentence}

\\paragraph{{Reliability gates.}} Supporting models eligible for substantive interpretation: {eligible_text}. Supporting models not eligible under the pre-specified gates: {ineligible_text}. Non-eligible estimates remain reported in Table~\\ref{{tab:reliability-gates}} rather than being omitted.
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
    cross_table = _write(generated / "table_cross_country.tex", _cross_country_table(cross))
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
