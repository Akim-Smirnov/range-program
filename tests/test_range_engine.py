from datetime import datetime, timedelta, timezone
from statistics import median

import pytest

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.services.range_engine import (
    RECALC_CENTER_COMPARISON_ORDER,
    RECALC_WIDTH_COMPARISON_ORDER,
    RangeEngine,
    RangeEngineError,
)


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


def test_calculate_range_sma_center() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(30):
        close = 100.0 + float(i)
        candles.append(_bar(t0, i, close))
    coin = Coin.create("TST", mode="balanced", center_method="sma", width_method="atr")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=200.0, candles=candles)
    last20 = [100.0 + float(i) for i in range(10, 30)]
    expected = sum(last20) / 20.0
    assert rr.center_method == "sma"
    assert rr.center == pytest.approx(expected)


def test_calculate_range_median_center() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    closes = list(range(1, 31))
    candles = [_bar(t0, i, float(c)) for i, c in enumerate(closes)]
    coin = Coin.create("TST", mode="balanced", center_method="median", width_method="atr")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=99.0, candles=candles)
    assert rr.center == pytest.approx(float(median(range(11, 31))))


def test_calculate_range_midpoint_center() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(25):
        base = 100.0 + i
        candles.append(
            Candle(
                timestamp=t0 + timedelta(hours=i),
                open=base,
                high=base + 2.0,
                low=base - 1.0,
                close=base,
                volume=1.0,
            )
        )
    coin = Coin.create("TST", mode="balanced", center_method="midpoint", width_method="atr")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=150.0, candles=candles)
    w = candles[-20:]
    hi = max(c.high for c in w)
    lo = min(c.low for c in w)
    assert rr.center == pytest.approx((hi + lo) / 2.0)


def test_calculate_range_donchian_center_matches_midpoint_for_same_window_mvp() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(25):
        base = 50.0 + i * 0.5
        candles.append(
            Candle(
                timestamp=t0 + timedelta(hours=i),
                open=base,
                high=base + 3.0,
                low=base - 2.0,
                close=base,
                volume=1.0,
            )
        )
    eng = RangeEngine()
    c_mid = Coin.create("TST", mode="balanced", center_method="midpoint", width_method="atr")
    c_don = Coin.create("TST", mode="balanced", center_method="donchian", width_method="atr")
    rr_mid = eng.calculate_range(c_mid, current_price=80.0, candles=candles)
    rr_don = eng.calculate_range(c_don, current_price=80.0, candles=candles)
    assert rr_mid.center == pytest.approx(rr_don.center)


def test_calculate_range_insufficient_candles_for_sma() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0 + i) for i in range(15)]
    coin = Coin.create("TST", center_method="sma", width_method="atr")
    eng = RangeEngine()
    with pytest.raises(RangeEngineError, match="минимум 20"):
        eng.calculate_range(coin, current_price=100.0, candles=candles)


def test_calculate_range_empty_candles() -> None:
    coin = Coin.create("TST", center_method="ema", width_method="atr")
    eng = RangeEngine()
    with pytest.raises(RangeEngineError, match="Нет свечей"):
        eng.calculate_range(coin, current_price=100.0, candles=[])


def test_calculate_range_std_width_positive() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0 + (i % 5) * 0.5) for i in range(40)]
    coin = Coin.create("TST", mode="balanced", center_method="ema", width_method="std")
    eng = RangeEngine()
    rr = eng.calculate_range(coin, current_price=110.0, candles=candles)
    assert rr.width_method == "std"
    assert rr.low < rr.center < rr.high
    assert rr.width_pct > 0


def test_calculate_range_donchian_width_matches_historical_mvp() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(30):
        base = 100.0 + i * 0.2
        candles.append(
            Candle(
                timestamp=t0 + timedelta(hours=i),
                open=base,
                high=base + 4.0,
                low=base - 1.0,
                close=base,
                volume=1.0,
            )
        )
    eng = RangeEngine()
    c_d = Coin.create("TST", mode="balanced", center_method="ema", width_method="donchian")
    c_h = Coin.create("TST", mode="balanced", center_method="ema", width_method="historical_range")
    r_d = eng.calculate_range(c_d, current_price=106.0, candles=candles)
    r_h = eng.calculate_range(c_h, current_price=106.0, candles=candles)
    assert r_d.center == pytest.approx(r_h.center)
    assert r_d.low == pytest.approx(r_h.low)
    assert r_d.high == pytest.approx(r_h.high)


def test_compare_width_methods_for_recalc_covers_all_four() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0 + i * 0.05) for i in range(50)]
    coin = Coin.create("TST", mode="balanced", center_method="ema", width_method="std")
    eng = RangeEngine()
    rows = eng.compare_width_methods_for_recalc(coin, current_price=102.0, candles=candles)
    assert len(rows) == len(RECALC_WIDTH_COMPARISON_ORDER)
    assert [m for m, _ in rows] == list(RECALC_WIDTH_COMPARISON_ORDER)
    for method, rr in rows:
        assert rr.width_method == method
        assert rr.low < rr.center < rr.high


def test_compare_center_methods_for_recalc_covers_all_six() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0 + i * 0.1) for i in range(50)]
    coin = Coin.create("TST", mode="balanced", center_method="median", width_method="atr")
    eng = RangeEngine()
    rows = eng.compare_center_methods_for_recalc(coin, current_price=105.0, candles=candles)
    assert len(rows) == len(RECALC_CENTER_COMPARISON_ORDER)
    assert [m for m, _ in rows] == list(RECALC_CENTER_COMPARISON_ORDER)
    for method, rr in rows:
        assert rr.center_method == method
        assert rr.low < rr.center < rr.high


def test_calculate_range_unknown_center_method() -> None:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(t0, i, 100.0) for i in range(50)]
    coin = Coin.create("TST", center_method="notamethod", width_method="atr")
    eng = RangeEngine()
    with pytest.raises(RangeEngineError, match="center_method"):
        eng.calculate_range(coin, current_price=100.0, candles=candles)
