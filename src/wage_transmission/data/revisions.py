"""Revision diagnostics for comparing two frozen processed-data vintages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RevisionSummary:
    """Summary statistics for one series across two data vintages."""

    series: str
    n_common: int
    n_revised: int
    n_added: int
    n_dropped: int
    max_abs_revision: float
    median_abs_revision: float

    def to_dict(self) -> dict[str, str | int | float]:
        """Convert the summary to JSON-compatible values."""
        return asdict(self)


def compare_vintages(
    old: pd.DataFrame,
    new: pd.DataFrame,
    *,
    value_columns: Iterable[str],
    key_columns: tuple[str, ...] = ("country", "year"),
    atol: float = 1e-12,
) -> tuple[pd.DataFrame, tuple[RevisionSummary, ...]]:
    """Compare named numeric series across two country-year data vintages.

    The output is long-form so additions, deletions, and numeric revisions remain visible rather
    than being collapsed into a single maximum-difference statistic.
    """
    values = tuple(dict.fromkeys(str(value) for value in value_columns))
    if not values:
        raise ValueError("At least one value column is required.")
    required = set(key_columns).union(values)
    missing_old = required.difference(old.columns)
    missing_new = required.difference(new.columns)
    if missing_old:
        raise ValueError(f"Old vintage is missing columns: {sorted(missing_old)}")
    if missing_new:
        raise ValueError(f"New vintage is missing columns: {sorted(missing_new)}")
    if old.duplicated(list(key_columns)).any() or new.duplicated(list(key_columns)).any():
        raise ValueError("Vintage comparison requires unique key rows in each input.")

    records: list[dict[str, str | int | float | None]] = []
    summaries: list[RevisionSummary] = []
    for series in values:
        left = old.loc[:, [*key_columns, series]].rename(columns={series: "old_value"})
        right = new.loc[:, [*key_columns, series]].rename(columns={series: "new_value"})
        merged = left.merge(right, on=list(key_columns), how="outer", indicator=True, validate="one_to_one")
        merged["old_value"] = pd.to_numeric(merged["old_value"], errors="coerce")
        merged["new_value"] = pd.to_numeric(merged["new_value"], errors="coerce")

        series_abs_revisions: list[float] = []
        n_revised = 0
        n_added = 0
        n_dropped = 0
        n_common = 0
        for row_dict in merged.to_dict(orient="records"):
            merge_status = str(row_dict["_merge"])
            old_value = row_dict["old_value"]
            new_value = row_dict["new_value"]
            old_numeric = None if pd.isna(old_value) else float(old_value)
            new_numeric = None if pd.isna(new_value) else float(new_value)

            absolute_revision: float | None = None
            relative_revision: float | None = None
            if merge_status == "left_only" or new_numeric is None:
                status = "dropped"
                n_dropped += 1
            elif merge_status == "right_only" or old_numeric is None:
                status = "added"
                n_added += 1
            else:
                n_common += 1
                absolute_revision = new_numeric - old_numeric
                if old_numeric != 0.0:
                    relative_revision = absolute_revision / abs(old_numeric)
                if np.isclose(old_numeric, new_numeric, atol=atol, rtol=0.0):
                    status = "unchanged"
                else:
                    status = "revised"
                    n_revised += 1
                    series_abs_revisions.append(abs(absolute_revision))

            record: dict[str, str | int | float | None] = {
                key: row_dict[key] for key in key_columns
            }
            record.update(
                {
                    "series": series,
                    "old_value": old_numeric,
                    "new_value": new_numeric,
                    "absolute_revision": absolute_revision,
                    "relative_revision": relative_revision,
                    "status": status,
                }
            )
            records.append(record)

        if series_abs_revisions:
            max_abs_revision = float(np.max(series_abs_revisions))
            median_abs_revision = float(np.median(series_abs_revisions))
        else:
            max_abs_revision = 0.0
            median_abs_revision = 0.0
        summaries.append(
            RevisionSummary(
                series=series,
                n_common=n_common,
                n_revised=n_revised,
                n_added=n_added,
                n_dropped=n_dropped,
                max_abs_revision=max_abs_revision,
                median_abs_revision=median_abs_revision,
            )
        )

    output = pd.DataFrame.from_records(records)
    if not output.empty:
        output = output.sort_values(["series", *key_columns]).reset_index(drop=True)
    return output, tuple(summaries)
