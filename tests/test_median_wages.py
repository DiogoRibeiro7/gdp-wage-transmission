from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wage_transmission.data.median_wages import (
    MedianWageSpec,
    assess_median_coverage,
    attach_median_wages,
    canonicalise_median_wages,
)

SPEC = MedianWageSpec(
    flow_ref="OECD.ELS.SAE,DSD_EARNINGS@DEC_I,1.0",
    key_template="{countries}..MEDIAN..",
    source="OECD_DEC_I_MEDIAN",
    label="Median gross earnings",
)


def _median_series(coverage_by_country: dict[str, int], *, start: int = 2000) -> pd.DataFrame:
    """A median series with a chosen number of observed years per country."""
    frames = []
    for country, years in coverage_by_country.items():
        observed = np.arange(start, start + years)
        frames.append(
            pd.DataFrame(
                {
                    "country": country,
                    "year": observed,
                    "median_wage": np.linspace(20000.0, 25000.0, len(observed)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_spec_refuses_an_empty_flow_reference() -> None:
    with pytest.raises(ValueError, match="must be supplied explicitly"):
        MedianWageSpec(
            flow_ref="   ", key_template="{countries}", source="X", label="Median earnings"
        )


def test_canonicalises_a_labelled_response() -> None:
    frame = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT"],
            "TIME_PERIOD": [2020, 2021],
            "OBS_VALUE": [21000.0, 21500.0],
        }
    )

    canonical = canonicalise_median_wages(frame, spec=SPEC)

    assert list(canonical.columns) == ["country", "year", "median_wage", "source"]
    assert canonical["source"].unique().tolist() == ["OECD_DEC_I_MEDIAN"]


def test_coverage_is_measured_per_country() -> None:
    median = _median_series({"AAA": 10, "BBB": 4})

    reports = {
        report.country: report
        for report in assess_median_coverage(median, start_year=2000, end_year=2009)
    }

    assert reports["AAA"].coverage == pytest.approx(1.0)
    assert reports["AAA"].eligible is True
    assert reports["BBB"].coverage == pytest.approx(0.4)
    assert reports["BBB"].eligible is False


def test_attachment_drops_countries_below_the_threshold() -> None:
    median = _median_series({"AAA": 10, "BBB": 4})
    panel = pd.DataFrame(
        {
            "country": ["AAA"] * 10 + ["BBB"] * 10,
            "year": list(range(2000, 2010)) * 2,
            "real_wage": 1.0,
        }
    )

    merged, coverage = attach_median_wages(panel, median, start_year=2000, end_year=2009)

    attached = merged.loc[merged["median_wage"].notna(), "country"].unique().tolist()
    assert attached == ["AAA"]
    # The excluded country is still reported: which countries were dropped changes the estimand.
    assert {report.country for report in coverage} == {"AAA", "BBB"}
    assert len(merged) == len(panel)


def test_attachment_fails_when_nothing_qualifies() -> None:
    median = _median_series({"AAA": 2, "BBB": 3})
    panel = pd.DataFrame(
        {"country": ["AAA"] * 10, "year": list(range(2000, 2010)), "real_wage": 1.0}
    )

    with pytest.raises(ValueError, match="coverage threshold"):
        attach_median_wages(panel, median, start_year=2000, end_year=2009)


def test_threshold_is_configurable() -> None:
    median = _median_series({"BBB": 5})
    panel = pd.DataFrame(
        {"country": ["BBB"] * 10, "year": list(range(2000, 2010)), "real_wage": 1.0}
    )

    merged, coverage = attach_median_wages(
        panel, median, start_year=2000, end_year=2009, min_coverage=0.5
    )

    assert coverage[0].eligible is True
    assert merged["median_wage"].notna().sum() == 5


def test_rejects_an_inverted_window() -> None:
    median = _median_series({"AAA": 5})

    with pytest.raises(ValueError, match="must not precede"):
        assess_median_coverage(median, start_year=2010, end_year=2000)


def test_rejects_a_series_without_the_value_column() -> None:
    median = _median_series({"AAA": 5}).drop(columns=["median_wage"])

    with pytest.raises(ValueError, match="missing columns"):
        assess_median_coverage(median, start_year=2000, end_year=2009)
