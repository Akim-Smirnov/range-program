"""Тесты backtest: валидация и прогон на синтетических свечах."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.services.backtest import run_backtest
from range_program.services.market_data import MarketDataService
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


def test_run_backtest_days_lt_1() -> None:
    coin = Coin.create("BTC")
    with pytest.raises(ValidationError, match="--days"):
        run_backtest(coin, 0, market=MarketDataService())


def test_run_backtest_insufficient_candles() -> None:
    coin = Coin.create("BTC", timeframe="1d")
    m = _FakeMarket(_candles_linear(5))
    with pytest.raises(ValidationError, match="Недостаточно свечей"):
        run_backtest(coin, 30, market=m)  # type: ignore[arg-type]


def test_run_backtest_completes_on_synthetic() -> None:
    coin = Coin.create("BTC", timeframe="1d", mode="balanced", center_method="ema", width_method="atr")
    m = _FakeMarket(_candles_linear(80))
    r = run_backtest(coin, 5, market=m)  # type: ignore[arg-type]
    assert r.symbol == "BTC"
    assert r.range_low < r.range_high
    assert r.lifetime_candles >= 1
    assert r.max_deviation_pct >= 0.0
