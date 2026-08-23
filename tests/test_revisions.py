from __future__ import annotations

import pandas as pd

from wage_transmission.data.revisions import compare_vintages


def test_compare_vintages_tracks_revision_addition_and_drop() -> None:
    old = pd.DataFrame(
        {
            "country": ["PRT", "PRT", "ESP"],
            "year": [2023, 2024, 2024],
            "real_wage": [100.0, 101.0, 200.0],
        }
    )
    new = pd.DataFrame(
        {
            "country": ["PRT", "PRT", "FRA"],
            "year": [2023, 2024, 2024],
            "real_wage": [100.0, 102.5, 180.0],
        }
    )
    revisions, summaries = compare_vintages(old, new, value_columns=["real_wage"])
    statuses = set(revisions["status"])
    assert statuses == {"unchanged", "revised", "added", "dropped"}
    summary = summaries[0]
    assert summary.n_revised == 1
    assert summary.n_added == 1
    assert summary.n_dropped == 1
    assert summary.max_abs_revision == 1.5
