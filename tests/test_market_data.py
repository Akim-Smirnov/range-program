from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from range_program.models.coin import Coin
from range_program.services.market_data import MarketDataError, MarketDataService


def test_pair_for_symbol() -> None:
    m = MarketDataService()
    assert m.pair_for_symbol("btc") == "BTC/USDT"
    assert m.pair_for_symbol("eth/usdt") == "ETH/USDT"


def test_pair_for_symbol_resolved() -> None:
    m = MarketDataService()
    now = datetime.now(timezone.utc)
    c = Coin.create(
        "HYPE",
        exchange="bybit",
        quote_asset="USDT",
        resolved_exchange="bybit",
        resolved_symbol_pair="HYPE/USDT",
        resolved_at=now,
    )
    assert m.pair_for_symbol("HYPE", coin=c) == "HYPE/USDT"


def test_get_current_price_uses_last() -> None:
    svc = MarketDataService()
    mock_ex = MagicMock()
    mock_ex.fetch_ticker.return_value = {"last": 123.45, "timestamp": 1_700_000_000_000}
    with patch.object(MarketDataService, "_get_exchange", return_value=mock_ex):
        assert svc.get_current_price("BTC") == 123.45


def test_get_ohlcv_parses_rows() -> None:
    svc = MarketDataService()
    mock_ex = MagicMock()
    mock_ex.fetch_ohlcv.return_value = [
        [1_700_000_000_000, 1, 2, 0.5, 1.5, 100.0],
    ]
    with patch.object(MarketDataService, "_get_exchange", return_value=mock_ex):
        candles = svc.get_ohlcv("BTC", "1h", 1)
    assert len(candles) == 1
    assert candles[0].open == 1.0
    assert candles[0].volume == 100.0


def test_get_ohlcv_empty_raises() -> None:
    svc = MarketDataService()
    mock_ex = MagicMock()
    mock_ex.fetch_ohlcv.return_value = []
    with patch.object(MarketDataService, "_get_exchange", return_value=mock_ex):
        with pytest.raises(MarketDataError, match="пустой"):
            svc.get_ohlcv("BTC", "1h", 5)


def test_resolve_market_prefers_exchange_first() -> None:
    """bybit первая в порядке, если задана в coin.exchange."""
    svc = MarketDataService()
    calls: list[tuple[str, str]] = []

    def fake_try(ex_id: str, pair: str):
        calls.append((ex_id, pair))
        if ex_id == "bybit" and pair == "ZZZ/USDT":
            return {"last": 1.0}
        return None

    with patch.object(MarketDataService, "_try_fetch_ticker", side_effect=fake_try):
        coin = Coin.create("ZZZ", exchange="bybit")
        m = svc.resolve_market(coin)
    assert m.exchange == "bybit"
    assert m.symbol_pair == "ZZZ/USDT"
    assert calls[0][0] == "bybit"


def test_resolve_market_prefers_quote_first() -> None:
    svc = MarketDataService()

    def fake_try(ex_id: str, pair: str):
        if ex_id == "binance" and pair == "ZZZ/USDC":
            return {"last": 1.0}
        return None

    with patch.object(MarketDataService, "_try_fetch_ticker", side_effect=fake_try):
        coin = Coin.create("ZZZ", quote_asset="USDC")
        m = svc.resolve_market(coin)
    assert m.symbol_pair == "ZZZ/USDC"


def test_resolve_market_not_found() -> None:
    svc = MarketDataService()
    with patch.object(MarketDataService, "_try_fetch_ticker", return_value=None):
        coin = Coin.create("NONEXISTENT999")
        with pytest.raises(MarketDataError, match="market not found"):
            svc.resolve_market(coin)


def test_resolve_market_fallback_tries_exchanges_in_order() -> None:
    """Без preferred: binance → bybit → … пока не сработает ticker."""
    svc = MarketDataService()
    order: list[tuple[str, str]] = []

    def fake_try(ex_id: str, pair: str):
        order.append((ex_id, pair))
        if ex_id == "okx" and pair == "AAA/USDT":
            return {"last": 1.0}
        return None

    with patch.object(MarketDataService, "_try_fetch_ticker", side_effect=fake_try):
        coin = Coin.create("AAA")
        m = svc.resolve_market(coin)
    assert m.exchange == "okx"
    assert m.symbol_pair == "AAA/USDT"
    assert order[0] == ("binance", "AAA/USDT")
    assert order[1] == ("bybit", "AAA/USDT")
    assert order[2] == ("okx", "AAA/USDT")


def test_resolve_market_fallback_tries_quotes_after_usdt() -> None:
    svc = MarketDataService()

    def fake_try(ex_id: str, pair: str):
        if ex_id == "binance" and pair == "BBB/USDC":
            return {"last": 1.0}
        return None

    with patch.object(MarketDataService, "_try_fetch_ticker", side_effect=fake_try):
        coin = Coin.create("BBB")
        m = svc.resolve_market(coin)
    assert m.symbol_pair == "BBB/USDC"
    assert m.quote_asset == "USDC"


def test_resolve_market_uses_cache_first() -> None:
    svc = MarketDataService()
    n = 0

    def fake_try(ex_id: str, pair: str):
        nonlocal n
        n += 1
        if ex_id == "kucoin" and pair == "X/USDT":
            return {"last": 1.0}
        return None

    with patch.object(MarketDataService, "_try_fetch_ticker", side_effect=fake_try):
        c0 = Coin.create("X")
        c0 = Coin(
            symbol="X",
            created_at=c0.created_at,
            mode=c0.mode,
            timeframe=c0.timeframe,
            lookback_days=c0.lookback_days,
            center_method=c0.center_method,
            width_method=c0.width_method,
            updated_at=c0.updated_at,
            resolved_exchange="kucoin",
            resolved_symbol_pair="X/USDT",
            resolved_at=c0.updated_at,
        )
        m = svc.resolve_market(c0)
    assert m.exchange == "kucoin"
    assert n == 1
