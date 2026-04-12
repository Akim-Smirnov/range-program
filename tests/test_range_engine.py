from datetime import datetime, timedelta, timezone

import pytest

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.services.range_engine import RangeEngine, RangeEngineError


def _bar(t0: datetime, i: int, close: float, spread: float = 1.0) -> Candle:
    ts = t0 + timedelta(hours=i)
    h = close + spread
    l = close - spread
    return Candle(timestamp=ts, open=close, high=h, low=l, close=close, volume=100.0)


def test_calculate_range_empty_grids_without_capital() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    c = 100.0
    for i in range(50):
        c += 0.1
        candles.append(_bar(t0, i, c))

    coin = Coin.create("TST", mode="balanced", center_method="ema", width_method="atr", capital=None)
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=c, candles=candles)
    assert rr.grid_configs == ()


def test_calculate_range_grids_with_capital() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    c = 100.0
    for i in range(50):
        c += 0.1
        candles.append(_bar(t0, i, c))

    coin = Coin.create("TST", mode="balanced", center_method="ema", width_method="atr", capital=1000.0)
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=c, candles=candles)
    assert len(rr.grid_configs) == 3
    assert {g.mode for g in rr.grid_configs} == {"aggressive", "balanced", "conservative"}
    assert all(g.grid_count >= 10 for g in rr.grid_configs)


def test_calculate_range_balanced_ema() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    c = 100.0
    for i in range(50):
        c += 0.1
        candles.append(_bar(t0, i, c))

    coin = Coin.create("TST", mode="balanced", center_method="ema", width_method="atr")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=c, candles=candles)
    assert rr.low < rr.center < rr.high
    assert rr.width_method == "atr"
    assert rr.center_method == "ema"
    assert rr.width_pct > 0


def test_calculate_range_price_center() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0 + i * 0.01) for i in range(50)]
    coin = Coin.create("TST", mode="aggressive", center_method="price", width_method="atr")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=123.45, candles=candles)
    assert rr.center == 123.45


def test_unsupported_width_method() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0) for i in range(50)]
    coin = Coin.create("TST", width_method="foo")
    eng = RangeEngine()
    with pytest.raises(RangeEngineError, match="не поддерживается"):
        eng.calculate_range(coin, current_price=100.0, candles=candles)
