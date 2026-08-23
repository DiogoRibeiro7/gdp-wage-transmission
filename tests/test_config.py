from __future__ import annotations

from pathlib import Path

import pytest

from wage_transmission.config import ModelsConfig, load_models_config, load_publication_config


def test_default_model_config_is_valid() -> None:
    config = ModelsConfig()
    assert config.distributed_lag.x_lags == 2
    assert config.structural_breaks.min_segment >= 4


def test_repo_model_config_loads() -> None:
    config = load_models_config(Path("config/models.yml"))
    assert config.local_projections.horizon == 8


def test_model_config_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("distributed_lag:\n  typo_lags: 2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_models_config(path)


def test_repo_publication_config_loads() -> None:
    config = load_publication_config(Path("config/publication.yml"))
    assert config.primary_country == "PRT"
