"""Typed project configuration loaders."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _StrictConfig(BaseModel):
    """Base model that rejects misspelled configuration keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DistributedLagConfig(_StrictConfig):
    x_lags: int = Field(default=2, ge=0)
    y_lags: int = Field(default=1, ge=0)
    hac_lags: int = Field(default=2, ge=0)


class ECMConfig(_StrictConfig):
    max_wage_growth_lags: int = Field(default=2, ge=0)
    max_productivity_growth_lags: int = Field(default=2, ge=0)
    hac_lags: int = Field(default=2, ge=0)


class StructuralBreakConfig(_StrictConfig):
    max_breaks: int = Field(default=3, ge=0)
    min_segment: int = Field(default=8, ge=4)


class StateSpaceConfig(_StrictConfig):
    initial_state_variance: float = Field(default=100.0, gt=0.0)


class LocalProjectionConfig(_StrictConfig):
    horizon: int = Field(default=8, ge=0)
    control_lags: int = Field(default=2, ge=0)
    hac_lags: int = Field(default=2, ge=0)


class AsymmetryConfig(_StrictConfig):
    lags: int = Field(default=2, ge=0)
    hac_lags: int = Field(default=2, ge=0)


class VECMConfig(_StrictConfig):
    k_ar_diff: int = Field(default=1, ge=1)
    irf_periods: int = Field(default=8, ge=1)


class ReliabilityConfig(_StrictConfig):
    """Minimum sample conditions for interpreting flexible specifications."""

    min_asymmetry_shocks_per_sign: int = Field(default=8, ge=3)
    min_local_projection_nobs: int = Field(default=25, ge=12)
    min_break_segment_for_interpretation: int = Field(default=10, ge=4)
    state_space_z_threshold: float = Field(default=1.96, gt=0.0)


class ModelsConfig(_StrictConfig):
    """Configuration for the core time-series model stack."""

    distributed_lag: DistributedLagConfig = DistributedLagConfig()
    ecm: ECMConfig = ECMConfig()
    structural_breaks: StructuralBreakConfig = StructuralBreakConfig()
    state_space: StateSpaceConfig = StateSpaceConfig()
    local_projections: LocalProjectionConfig = LocalProjectionConfig()
    asymmetry: AsymmetryConfig = AsymmetryConfig()
    vecm: VECMConfig = VECMConfig()
    reliability: ReliabilityConfig = ReliabilityConfig()


class PublicationConfig(_StrictConfig):
    """Pre-specified hierarchy for publication-facing interpretation."""

    schema_version: int = Field(default=1, ge=1)
    primary_country: str = Field(default="PRT", min_length=3, max_length=3)
    primary_driver: str = Field(default="productivity_per_worker", min_length=1)
    secondary_drivers: tuple[str, ...] = ("productivity",)
    primary_estimand: str = Field(default="distributed_lag_cumulative", min_length=1)
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    cross_country_primary_object: str = Field(default="country_specific_estimates", min_length=1)
    cross_country_summary_estimator: str = Field(default="random_effects", min_length=1)
    ecm_policy: str = Field(default="reliability_gated", min_length=1)
    state_space_policy: str = Field(default="reliability_gated", min_length=1)
    structural_break_policy: str = Field(default="reliability_gated", min_length=1)
    local_projection_policy: str = Field(default="supported_horizons_only", min_length=1)
    asymmetry_policy: str = Field(default="reliability_gated", min_length=1)
    decomposition_policy: str = Field(default="accounting_identity_not_causal", min_length=1)


def load_publication_config(path: Path) -> PublicationConfig:
    """Load and validate the publication specification hierarchy."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Publication configuration must be a YAML mapping.")
    return PublicationConfig.model_validate(payload)


def load_models_config(path: Path) -> ModelsConfig:
    """Load and validate a YAML model configuration file."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Model configuration must be a YAML mapping.")
    return ModelsConfig.model_validate(payload)
