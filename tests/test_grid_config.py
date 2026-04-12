"""Капитал, GridConfig, геометрическая сетка в RangeEngine и JSON."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from range_program.models.grid_config import GridConfig
from range_program.models.recommended_range import RecommendedRange
from range_program.repositories.coin_repository import CoinRepository
from range_program.services.coin_service import CoinService
from range_program.services.range_engine import RangeEngineError, compute_geometric_grid_configs
from range_program.validation import ValidationError


def test_compute_geometric_grid_configs_clamp() -> None:
    cfgs = compute_geometric_grid_configs(width_pct=100.0, capital=1000.0)
    assert len(cfgs) == 3
    assert cfgs[0].mode == "aggressive"
    assert cfgs[0].step_pct == 0.5
    raw = round(100.0 / 0.5)
    assert cfgs[0].grid_count == min(120, max(10, raw))
    assert cfgs[0].order_size == round(1000.0 / cfgs[0].grid_count, 2)


def test_compute_geometric_rejects_bad_width() -> None:
    with pytest.raises(RangeEngineError, match="width_pct"):
        compute_geometric_grid_configs(0.0, 1000.0)


def test_compute_geometric_rejects_bad_capital() -> None:
    with pytest.raises(RangeEngineError, match="Капитал"):
        compute_geometric_grid_configs(20.0, 0.0)


def test_recommended_range_json_roundtrip(tmp_path: Path) -> None:
    repo = CoinRepository(tmp_path / "c.json")
    rr = RecommendedRange(
        low=61000.0,
        high=78000.0,
        center=69500.0,
        width_pct=24.5,
        calculated_at=datetime(2026, 4, 12, tzinfo=timezone.utc),
        center_method="ema",
        width_method="atr",
        grid_configs=(
            GridConfig(mode="aggressive", grid_count=49, step_pct=0.5, order_size=20.41),
            GridConfig(mode="balanced", grid_count=31, step_pct=0.8, order_size=32.26),
            GridConfig(mode="conservative", grid_count=18, step_pct=1.4, order_size=55.56),
        ),
    )
    assert repo.add_coin("BTC", capital=1000.0) is True
    c0 = repo.get_coin("BTC")
    assert c0 is not None
    assert repo.update_coin(replace(c0, recommended_range=rr)) is True

    repo2 = CoinRepository(tmp_path / "c.json")
    loaded = repo2.get_coin("BTC")
    assert loaded is not None
    assert loaded.capital == 1000.0
    assert loaded.recommended_range is not None
    assert len(loaded.recommended_range.grid_configs) == 3
    assert loaded.recommended_range.grid_configs[0].mode == "aggressive"

    raw = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert raw[0]["capital"] == 1000.0
    assert len(raw[0]["recommended_range"]["grid_configs"]) == 3


def test_legacy_recommended_range_without_grid_configs(tmp_path: Path) -> None:
    legacy = [
        {
            "symbol": "ETH",
            "created_at": "2025-01-01T12:00:00+00:00",
            "updated_at": "2025-01-01T12:00:00+00:00",
            "recommended_range": {
                "low": 1.0,
                "high": 2.0,
                "center": 1.5,
                "width_pct": 66.67,
                "calculated_at": "2025-01-02T12:00:00+00:00",
                "center_method": "ema",
                "width_method": "atr",
            },
        }
    ]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(legacy), encoding="utf-8")
    repo = CoinRepository(p)
    c = repo.get_coin("ETH")
    assert c is not None
    assert c.recommended_range is not None
    assert c.recommended_range.grid_configs == ()


def test_coin_service_set_clear_capital(tmp_path: Path) -> None:
    repo = CoinRepository(tmp_path / "c.json")
    repo.add_coin("BTC")
    svc = CoinService(repo)
    c = svc.set_capital("BTC", 1500.0)
    assert c.capital == 1500.0
    c2 = svc.clear_capital("BTC")
    assert c2.capital is None


def test_coin_service_set_capital_validation(tmp_path: Path) -> None:
    repo = CoinRepository(tmp_path / "c.json")
    repo.add_coin("BTC")
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="capital"):
        svc.set_capital("BTC", -1.0)
