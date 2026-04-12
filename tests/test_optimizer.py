"""Тесты compare_modes и compute_mode_score."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.services.optimizer import (
    MODES_COMPARISON_ORDER,
    best_mode_result,
    compare_modes,
    compute_mode_score,
)
from range_program.validation import ValidationError


def _candles_linear(n: int, start: float = 100.0, step: float = 0.2) -> list[Candle]:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        base = start + i * step
        ts = t0 + timedelta(hours=i)
        out.append(
            Candle(
                timestamp=ts,
                open=base,
                high=base + 0.5,
                low=base - 0.5,
                close=base,
                volume=1.0,
            )
        )
    return out


class _FakeMarket:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int, *, coin: Coin | None = None
    ) -> list[Candle]:
        return self._candles[-limit:] if len(self._candles) >= limit else self._candles


def test_compute_mode_score_formula() -> None:
    s = compute_mode_score(
        lifetime_days=10.0,
        ok_days=4.0,
        stale_days=2.0,
        max_deviation_pct=5.0,
    )
    expected = 10.0 + 4.0 * 0.5 - 2.0 * 0.7 - 5.0 * 0.2
    assert abs(s - expected) < 1e-9


def test_compare_modes_returns_three_ordered() -> None:
    coin = Coin.create("BTC", timeframe="1d", mode="balanced", center_method="ema", width_method="atr")
    m = _FakeMarket(_candles_linear(80))
    rows = compare_modes(coin, 5, market=m)  # type: ignore[arg-type]
    assert len(rows) == 3
    assert [r.mode for r in rows] == list(MODES_COMPARISON_ORDER)
    assert all(len(r.summary) > 0 for r in rows)
    b = best_mode_result(rows)
    assert b is not None
    assert b.mode in MODES_COMPARISON_ORDER


def test_compare_modes_propagates_validation_too_long_window() -> None:
    """1m + большой --days требует >1000 свечей — run_backtest должен отказать."""
    coin = Coin.create("BTC", timeframe="1m", mode="balanced", center_method="ema", width_method="atr")
    m = _FakeMarket(_candles_linear(2000))
    with pytest.raises(ValidationError, match="максимум"):
        compare_modes(coin, 365, market=m)  # type: ignore[arg-type]
