from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from range_program.models.candle import Candle
from range_program.models.market_symbol_match import MarketSymbolMatch
from range_program.repositories.coin_repository import CoinRepository
from range_program.services.coin_service import CoinService
from range_program.services.market_data import PriceQuote
from range_program.services.recalc_service import RecalcService, estimate_candle_limit
from range_program.validation import ValidationError


def _make_candles(n: int, *, start: float = 100.0) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        close = start + float(i)
        out.append(
            Candle(
                timestamp=base + timedelta(hours=i),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
            )
        )
    return out


class _FakeMarket:
    def __init__(self, candles: list[Candle], *, price: float = 123.0) -> None:
        self._candles = candles
        self._price = price
        self._match = MarketSymbolMatch(exchange="binance", symbol_pair="BTC/USDT", quote_asset="USDT")

    def resolve_market(self, coin) -> MarketSymbolMatch:  # noqa: ANN001
        return self._match

    def fetch_ohlcv_with_match(self, match: MarketSymbolMatch, timeframe: str, limit: int) -> list[Candle]:
        return list(self._candles[:limit])

    def fetch_price_quote_with_match(self, match: MarketSymbolMatch) -> PriceQuote:
        return PriceQuote(price=float(self._price), as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    return tmp_path / "coins.json"


def test_estimate_candle_limit_is_adaptive_for_large_timeframes() -> None:
    # Для 1d и 30 дней: bpd=1, raw=30*1+5=35. Старый фиксированный минимум 80 тут не нужен.
    assert estimate_candle_limit("1d", 30) == 35


def test_recalc_validates_candle_count_before_engine(repo_path: Path) -> None:
    coins = CoinService(CoinRepository(repo_path))
    ok, _ = coins.add_coin("BTC", timeframe="1d", lookback_days=1, center_method="sma", width_method="atr")
    assert ok

    market = _FakeMarket(_make_candles(10), price=150.0)
    svc = RecalcService(coins, market)

    with pytest.raises(ValidationError, match=r"Слишком мало свечей.*получено 10.*минимум 20"):
        svc.recalc("BTC", save=False)


def test_recalc_overrides_can_run_without_saving(repo_path: Path) -> None:
    coins = CoinService(CoinRepository(repo_path))
    ok, _ = coins.add_coin("BTC", timeframe="4h", lookback_days=10, center_method="price", width_method="atr")
    assert ok

    market = _FakeMarket(_make_candles(40), price=200.0)
    svc = RecalcService(coins, market)

    out = svc.recalc("BTC", timeframe="1d", lookback_days=1, center_method="sma", width_method="atr", save=False)
    assert out.symbol == "BTC"
    assert out.recommended is not None

    # Ничего не сохраняем в монету: настройки и recommended_range остаются прежними/пустыми.
    c = coins.get_coin("BTC")
    assert c is not None
    assert c.timeframe == "4h"
    assert c.lookback_days == 10
    assert c.center_method == "price"
    assert c.width_method == "atr"
    assert c.recommended_range is None


def test_recalc_overrides_can_be_saved(repo_path: Path) -> None:
    coins = CoinService(CoinRepository(repo_path))
    ok, _ = coins.add_coin("BTC", timeframe="4h", lookback_days=10, center_method="price", width_method="atr")
    assert ok

    market = _FakeMarket(_make_candles(40), price=200.0)
    svc = RecalcService(coins, market)

    out = svc.recalc("BTC", timeframe="1d", lookback_days=1, center_method="sma", width_method="atr", save=True)
    assert out.recommended is not None

    c = coins.get_coin("BTC")
    assert c is not None
    assert c.timeframe == "1d"
    assert c.lookback_days == 1
    assert c.center_method == "sma"
    assert c.width_method == "atr"
    assert c.recommended_range is not None


def test_recalc_rejects_invalid_override_timeframe(repo_path: Path) -> None:
    coins = CoinService(CoinRepository(repo_path))
    ok, _ = coins.add_coin("BTC")
    assert ok

    market = _FakeMarket(_make_candles(40), price=200.0)
    svc = RecalcService(coins, market)

    with pytest.raises(ValidationError, match="timeframe"):
        svc.recalc("BTC", timeframe="bad_tf", save=False)
