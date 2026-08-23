"""Shared typed result containers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RegressionCoefficient:
    """One estimated coefficient with uncertainty."""

    name: str
    estimate: float
    std_error: float
    p_value: float


@dataclass(frozen=True)
class ModelSummary:
    """Serializable common model summary."""

    model: str
    nobs: int
    coefficients: tuple[RegressionCoefficient, ...]
    diagnostics: dict[str, float | int | str | bool]

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to JSON-compatible Python objects."""
        return asdict(self)
