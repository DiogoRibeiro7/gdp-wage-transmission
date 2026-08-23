"""Input validation and canonical transformations."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_LEVEL_COLUMNS = ("year", "real_wage", "productivity")


def validate_level_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and sort one-country annual level data.

    Parameters
    ----------
    frame:
        DataFrame containing positive `real_wage` and `productivity` levels.

    Returns
    -------
    pandas.DataFrame
        A defensive, year-sorted copy.
    """
    missing = set(REQUIRED_LEVEL_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    clean = frame.loc[:, list(REQUIRED_LEVEL_COLUMNS)].copy()
    clean["year"] = pd.to_numeric(clean["year"], errors="raise").astype(int)
    clean["real_wage"] = pd.to_numeric(clean["real_wage"], errors="coerce")
    clean["productivity"] = pd.to_numeric(clean["productivity"], errors="coerce")
    clean = clean.dropna().sort_values("year").reset_index(drop=True)

    if clean["year"].duplicated().any():
        raise ValueError("The input contains duplicate years.")
    if len(clean) < 12:
        raise ValueError("At least 12 complete annual observations are required.")
    if (clean[["real_wage", "productivity"]] <= 0).any().any():
        raise ValueError("Level variables must be strictly positive before logging.")

    return clean


def add_log_growth_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add log levels and one-period log growth rates."""
    clean = validate_level_frame(frame)
    clean["log_wage"] = np.log(clean["real_wage"].to_numpy(dtype=float))
    clean["log_productivity"] = np.log(clean["productivity"].to_numpy(dtype=float))
    clean["dlog_wage"] = clean["log_wage"].diff()
    clean["dlog_productivity"] = clean["log_productivity"].diff()
    return clean
