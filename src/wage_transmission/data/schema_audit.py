"""Record the source schema attributes that canonicalisation discards.

:func:`wage_transmission.data.common.canonical_observations` deliberately reduces a labelled
SDMX response to ``country``, ``year``, one value column and a source tag. That narrowness is
what makes the analytical panel safe to model, but it also means the unit, price base,
observation status and any revision flag attached to each observation disappear before anything
is estimated.

This module captures those attributes *before* the reduction, so a published number can be
traced back to the exact measurement concept it came from. Two rules apply.

A series carrying more than one unit or price base is **ambiguous**, not merely varied: mixing
current and constant prices, or two currency bases, silently changes the economic concept.
Ambiguity raises rather than warns.

Observation status and revision flags are expected to vary -- provisional, estimated and
revised observations are normal in official statistics -- so they are recorded in full rather
than treated as errors. Recording them is what makes a later revision visible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

# Concept-changing attributes: more than one value in a single series is a defect.
CONCEPT_ATTRIBUTES = ("unit", "price_base")
# Descriptive attributes: variation is expected and is the point of recording them.
DESCRIPTIVE_ATTRIBUTES = ("observation_status", "transformation", "revision")

# SDMX responses carry either coded or labelled columns depending on the requested format.
_COLUMN_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "unit": ("UNIT_MEASURE", "Unit of measure", "UNIT", "unit"),
    "price_base": ("PRICE_BASE", "Price base"),
    "observation_status": ("OBS_STATUS", "Observation status"),
    "transformation": ("TRANSFORMATION", "Transformation"),
    "revision": ("REVISION", "Revision", "OBS_REVISION", "REV_FLAG"),
}


@dataclass(frozen=True)
class SeriesSchema:
    """The measurement attributes behind one canonical series."""

    source: str
    value_name: str
    n_observations: int
    n_countries: int
    first_year: int
    last_year: int
    units: tuple[str, ...]
    price_bases: tuple[str, ...]
    observation_statuses: tuple[str, ...]
    transformations: tuple[str, ...]
    revision_flags: tuple[str, ...]
    attributes_present: tuple[str, ...]
    attributes_absent: tuple[str, ...]


def _distinct(frame: pd.DataFrame, attribute: str) -> tuple[str, ...]:
    """Distinct non-empty values of an attribute, whichever column name carries it."""
    for column in _COLUMN_CANDIDATES[attribute]:
        if column not in frame.columns:
            continue
        values = frame[column].dropna().astype(str).str.strip()
        values = values.loc[values != ""]
        return tuple(sorted(values.unique().tolist()))
    return ()


def audit_series_schema(
    frame: pd.DataFrame,
    *,
    source: str,
    value_name: str,
) -> SeriesSchema:
    """Summarise the schema attributes of one labelled source response.

    Raises
    ------
    ValueError
        If the response carries more than one unit or price base, which would mean the series
        mixes measurement concepts, or if the SDMX identity columns are absent.
    """
    required = {"REF_AREA", "TIME_PERIOD"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Schema audit requires SDMX columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"Schema audit received no observations for {source}.")

    collected = {attribute: _distinct(frame, attribute) for attribute in _COLUMN_CANDIDATES}
    for attribute in CONCEPT_ATTRIBUTES:
        values = collected[attribute]
        if len(values) > 1:
            raise ValueError(
                f"{source} mixes more than one {attribute.replace('_', ' ')}: {list(values)}. "
                "Refine the source key rather than aggregating across measurement concepts."
            )

    years = pd.to_numeric(frame["TIME_PERIOD"], errors="coerce").dropna().astype(int)
    if years.empty:
        raise ValueError(f"Schema audit found no usable TIME_PERIOD values for {source}.")

    present = tuple(name for name, values in collected.items() if values)
    absent = tuple(name for name in _COLUMN_CANDIDATES if name not in present)

    return SeriesSchema(
        source=source,
        value_name=value_name,
        n_observations=len(frame),
        n_countries=int(frame["REF_AREA"].nunique()),
        first_year=int(years.min()),
        last_year=int(years.max()),
        units=collected["unit"],
        price_bases=collected["price_base"],
        observation_statuses=collected["observation_status"],
        transformations=collected["transformation"],
        revision_flags=collected["revision"],
        attributes_present=present,
        attributes_absent=absent,
    )


def schema_audit_frame(schemas: Sequence[SeriesSchema]) -> pd.DataFrame:
    """Render audited schemas as a flat, diffable table."""
    if not schemas:
        raise ValueError("No series schemas to render.")
    records = []
    for schema in schemas:
        record: dict[str, object] = {}
        for key, value in asdict(schema).items():
            record[key] = "; ".join(value) if isinstance(value, tuple) else value
        records.append(record)
    return pd.DataFrame.from_records(records)


def write_schema_audit(schemas: Sequence[SeriesSchema], output: Path) -> Path:
    """Write the schema audit to CSV."""
    frame = schema_audit_frame(schemas)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output
