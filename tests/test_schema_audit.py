from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from wage_transmission.data.schema_audit import (
    SeriesSchema,
    audit_series_schema,
    schema_audit_frame,
    write_schema_audit,
)


def _labelled_response(**overrides: object) -> pd.DataFrame:
    """A labelled SDMX-style response of the shape the OECD client returns."""
    frame = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT", "ESP", "ESP"],
            "TIME_PERIOD": [2020, 2021, 2020, 2021],
            "OBS_VALUE": [1.0, 2.0, 3.0, 4.0],
            "Unit of measure": ["US dollars, PPP converted"] * 4,
            "Price base": ["Constant prices"] * 4,
            "Observation status": ["Normal value", "Provisional value", "Normal value", ""],
        }
    )
    for column, value in overrides.items():
        frame[column] = value
    return frame


def test_records_the_attributes_canonicalisation_discards() -> None:
    schema = audit_series_schema(
        _labelled_response(), source="OECD_PDB_GDPHRS", value_name="productivity"
    )

    assert schema.units == ("US dollars, PPP converted",)
    assert schema.price_bases == ("Constant prices",)
    assert schema.n_countries == 2
    assert schema.first_year == 2020
    assert schema.last_year == 2021
    assert schema.n_observations == 4


def test_observation_status_variation_is_recorded_not_rejected() -> None:
    """Provisional and revised observations are normal; recording them is the point."""
    schema = audit_series_schema(
        _labelled_response(), source="OECD_PDB_GDPHRS", value_name="productivity"
    )

    assert schema.observation_statuses == ("Normal value", "Provisional value")


def test_mixed_units_fail_loudly() -> None:
    frame = _labelled_response()
    frame.loc[0, "Unit of measure"] = "Euro"

    with pytest.raises(ValueError, match="mixes more than one unit"):
        audit_series_schema(frame, source="OECD_PDB_GDPHRS", value_name="productivity")


def test_mixed_price_bases_fail_loudly() -> None:
    frame = _labelled_response()
    frame.loc[0, "Price base"] = "Current prices"

    with pytest.raises(ValueError, match="mixes more than one price base"):
        audit_series_schema(frame, source="OECD_AV_AN_WAGE", value_name="real_wage")


def test_absent_attributes_are_reported_rather_than_assumed() -> None:
    frame = _labelled_response().drop(columns=["Price base"])

    schema = audit_series_schema(frame, source="OECD_PDB_GDPHRS", value_name="productivity")

    assert schema.price_bases == ()
    assert "price_base" in schema.attributes_absent
    assert "unit" in schema.attributes_present


def test_coded_columns_are_read_when_labels_are_absent() -> None:
    frame = pd.DataFrame(
        {
            "REF_AREA": ["PRT"],
            "TIME_PERIOD": [2020],
            "OBS_VALUE": [1.0],
            "UNIT_MEASURE": ["USD_PPP_H"],
            "PRICE_BASE": ["Q"],
            "OBS_STATUS": ["A"],
        }
    )

    schema = audit_series_schema(frame, source="OECD_PDB_GDPHRS", value_name="productivity")

    assert schema.units == ("USD_PPP_H",)
    assert schema.price_bases == ("Q",)
    assert schema.observation_statuses == ("A",)


def test_requires_the_sdmx_identity_columns() -> None:
    frame = _labelled_response().drop(columns=["REF_AREA"])

    with pytest.raises(ValueError, match="requires SDMX columns"):
        audit_series_schema(frame, source="OECD_PDB_GDPHRS", value_name="productivity")


def test_rejects_an_empty_response() -> None:
    frame = _labelled_response().head(0)

    with pytest.raises(ValueError, match="no observations"):
        audit_series_schema(frame, source="OECD_PDB_GDPHRS", value_name="productivity")


def test_audit_renders_and_writes_a_flat_table(tmp_path: Path) -> None:
    schemas: list[SeriesSchema] = [
        audit_series_schema(
            _labelled_response(), source="OECD_PDB_GDPHRS", value_name="productivity"
        ),
        audit_series_schema(_labelled_response(), source="OECD_AV_AN_WAGE", value_name="real_wage"),
    ]

    frame = schema_audit_frame(schemas)
    assert len(frame) == 2
    assert frame.loc[0, "observation_statuses"] == "Normal value; Provisional value"

    output = write_schema_audit(schemas, tmp_path / "audit" / "schema.csv")
    assert output.is_file()
    assert len(pd.read_csv(output)) == 2
