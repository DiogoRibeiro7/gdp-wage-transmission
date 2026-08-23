from __future__ import annotations

import pandas as pd
import pytest

from wage_transmission.validation import add_log_growth_columns, validate_level_frame


def test_validate_rejects_nonpositive_levels() -> None:
    frame = pd.DataFrame(
        {
            "year": range(2000, 2012),
            "real_wage": [1.0] * 11 + [0.0],
            "productivity": [2.0] * 12,
        }
    )
    with pytest.raises(ValueError, match="strictly positive"):
        validate_level_frame(frame)


def test_log_growth_columns(synthetic_levels: pd.DataFrame) -> None:
    transformed = add_log_growth_columns(synthetic_levels)
    assert transformed["dlog_wage"].isna().sum() == 1
    assert transformed["dlog_productivity"].isna().sum() == 1
