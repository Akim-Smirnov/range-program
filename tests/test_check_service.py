"""Тесты сервиса проверки монеты (CheckService): recalc-логика, persist и ошибки."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from range_program.check_all_report import CheckTableRow
from range_program.models.active_range import ActiveRange
from range_program.models.check_result import CheckResult
from range_program.models.coin import Coin
from range_program.models.market_symbol_match import MarketSymbolMatch
from range_program.models.recommended_range import RecommendedRange
from range_program.services.check_service import CheckService
from range_program.services.recommended_range_freshness import (
    is_recommended_range_stale,
    recommended_range_ttl_for_timeframe,
)
from range_program.validation import ValidationError


def _dt(h: int = 0, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 1, 1, h, m, s, tzinfo=timezone.utc)


def _rr(calculated_at: datetime) -> RecommendedRange:
    return RecommendedRange(
        low=90.0,
        high=110.0,
        center=100.0,
        width_pct=20.0,
        calculated_at=calculated_at,
        center_method="ema",
        width_method="atr",
    )


def _coin(symbol: str = "BTC", *, timeframe: str = "4h", with_rr: bool = True, rr_dt: datetime | None = None) -> Coin:
    c = Coin.create(symbol, timeframe=timeframe)
    ar = ActiveRange(low=95.0, high=105.0, set_at=_dt())
    rr = _rr(rr_dt or _dt()) if with_rr else None
    return replace(c, active_range=ar, recommended_range=rr)


class _FakeCoins:
    def __init__(self, coins: list[Coin]) -> None:
        self._coins = {c.symbol: c for c in coins}
        self.updated: list[Coin] = []

    def get_coin(self, symbol: str) -> Coin | None:
        return self._coins.get(Coin.normalize_symbol(symbol))

    def update_coin(self, coin: Coin) -> bool:
        self._coins[coin.symbol] = coin
        self.updated.append(coin)
        return True

    def list_coins(self) -> list[Coin]:
        return list(self._coins.values())


class _FakeMarket:
    def resolve_market(self, coin: Coin) -> MarketSymbolMatch:
        return MarketSymbolMatch(exchange="binance", symbol_pair=f"{coin.symbol}/USDT", quote_asset="USDT")

    def fetch_price_quote_with_match(self, match: MarketSymbolMatch):  # noqa: ANN001
        class _Quote:
            price = 100.0

        return _Quote()


class _FakeEvaluator:
    def evaluate(self, coin: Coin, current_price: float) -> CheckResult:
        return CheckResult(
            symbol=coin.symbol,
            current_price=current_price,
            active_low=95.0,
            active_high=105.0,
            active_center=100.0,
            recommended_low=90.0,
            recommended_high=110.0,
            recommended_center=100.0,
            distance_to_lower_pct=5.0,
            distance_to_upper_pct=5.0,
            deviation_from_active_center_pct=0.0,
            status="OK",
            recommendation="ok",
            checked_at=_dt(),
        )


class _FakeRecalc:
    def __init__(self, coins: _FakeCoins) -> None:
        self.calls: list[str] = []
        self._coins = coins

    def recalc(self, symbol: str) -> None:
        sym = Coin.normalize_symbol(symbol)
        self.calls.append(sym)
        c = self._coins.get_coin(sym)
        assert c is not None
        self._coins.update_coin(replace(c, recommended_range=_rr(_dt(10))))


def test_recommended_range_ttl_by_timeframe() -> None:
    assert recommended_range_ttl_for_timeframe("1h") == timedelta(hours=12)
    assert recommended_range_ttl_for_timeframe("4h") == timedelta(hours=24)
    assert recommended_range_ttl_for_timeframe("1d") == timedelta(hours=72)


def test_recommended_range_ttl_fallback_for_custom_timeframe() -> None:
    assert recommended_range_ttl_for_timeframe("15m") == timedelta(hours=1, minutes=30)
    assert recommended_range_ttl_for_timeframe("2h") == timedelta(hours=12)
    assert recommended_range_ttl_for_timeframe("custom") == timedelta(hours=24)


@pytest.mark.parametrize(
    ("timeframe", "ttl"),
    [("1h", timedelta(hours=12)), ("4h", timedelta(hours=24)), ("1d", timedelta(hours=72))],
)
def test_stale_boundary_cases(timeframe: str, ttl: timedelta) -> None:
    calculated_at = _dt(0, 0, 0)
    at_edge = calculated_at + ttl
    just_fresh = at_edge - timedelta(seconds=1)
    just_stale = at_edge + timedelta(seconds=1)
    assert is_recommended_range_stale(calculated_at=calculated_at, timeframe=timeframe, now_utc=at_edge) is True
    assert is_recommended_range_stale(calculated_at=calculated_at, timeframe=timeframe, now_utc=just_fresh) is False
    assert is_recommended_range_stale(calculated_at=calculated_at, timeframe=timeframe, now_utc=just_stale) is True


def test_stale_handles_naive_datetime_as_utc() -> None:
    naive_calculated_at = datetime(2026, 1, 1, 0, 0, 0)
    now_utc = _dt(12, 0, 0)
    assert is_recommended_range_stale(calculated_at=naive_calculated_at, timeframe="1h", now_utc=now_utc) is True


class _FakeHistory:
    def __init__(self) -> None:
        self.saved: list[CheckResult] = []

    def save_check(self, result: CheckResult) -> None:
        self.saved.append(result)


def _build_service(
    coin: Coin,
    now_utc: datetime,
    *,
    history: _FakeHistory | None = None,
) -> tuple[CheckService, _FakeRecalc, _FakeCoins]:
    coins = _FakeCoins([coin])
    recalc = _FakeRecalc(coins)
    service = CheckService(
        coins=coins,
        market=_FakeMarket(),
        recalc=recalc,
        evaluator=_FakeEvaluator(),
        history=history,
        now_provider=lambda: now_utc,
    )
    return service, recalc, coins


def test_run_check_recalc_when_recommended_range_missing() -> None:
    service, recalc, _ = _build_service(_coin(with_rr=False), _dt(12))
    result = service.run_check("BTC")
    assert result.symbol == "BTC"
    assert recalc.calls == ["BTC"]


def test_run_check_can_skip_auto_recalc_when_stale() -> None:
    service, recalc, _ = _build_service(_coin(rr_dt=_dt(0)), _dt(0) + timedelta(hours=24))
    service.run_check("BTC", auto_recalc=False)
    assert recalc.calls == []


def test_run_check_skip_auto_recalc_fails_when_missing_recommended_range() -> None:
    service, recalc, _ = _build_service(_coin(with_rr=False), _dt(12))
    with pytest.raises(ValidationError, match="Автоматический recalc отключён"):
        service.run_check("BTC", auto_recalc=False)
    assert recalc.calls == []

def test_run_check_skips_recalc_when_recommended_range_fresh() -> None:
    service, recalc, _ = _build_service(_coin(rr_dt=_dt(0)), _dt(10))
    service.run_check("BTC")
    assert recalc.calls == []


def test_run_check_recalc_when_recommended_range_stale() -> None:
    service, recalc, _ = _build_service(_coin(rr_dt=_dt(0)), _dt(0) + timedelta(hours=24))
    service.run_check("BTC")
    assert recalc.calls == ["BTC"]


def test_run_check_side_effects_after_missing_auto_recalc() -> None:
    history = _FakeHistory()
    service, recalc, coins = _build_service(_coin(with_rr=False), _dt(12), history=history)
    result = service.run_check("BTC")
    assert recalc.calls == ["BTC"]
    assert coins.updated, "update_coin should be called"
    updated_coin = coins.get_coin("BTC")
    assert updated_coin is not None
    assert updated_coin.last_check == result
    assert history.saved == [result]


def test_run_check_side_effects_after_stale_auto_recalc() -> None:
    history = _FakeHistory()
    service, recalc, coins = _build_service(_coin(rr_dt=_dt(0)), _dt(0) + timedelta(hours=24), history=history)
    result = service.run_check("BTC")
    assert recalc.calls == ["BTC"]
    assert len(coins.updated) >= 2, "one update in recalc and one after check"
    updated_coin = coins.get_coin("BTC")
    assert updated_coin is not None
    assert updated_coin.last_check == result
    assert history.saved == [result]


def test_run_check_all_recalc_only_missing_or_stale() -> None:
    now = _dt(12)
    fresh = _coin("ETH", rr_dt=_dt(6))
    missing = _coin("BTC", with_rr=False)
    stale = _coin("SOL", rr_dt=_dt(0), timeframe="1h")
    coins = _FakeCoins([missing, fresh, stale])
    recalc = _FakeRecalc(coins)
    service = CheckService(
        coins=coins,
        market=_FakeMarket(),
        recalc=recalc,
        evaluator=_FakeEvaluator(),
        now_provider=lambda: now,
    )

    rows = service.run_check_all()

    assert len(rows) == 3
    assert all(isinstance(row, CheckTableRow) for row in rows)
    assert {row.symbol for row in rows} == {"BTC", "ETH", "SOL"}
    assert sorted(recalc.calls) == ["BTC", "SOL"]


def test_run_check_dry_run_does_not_persist(tmp_path) -> None:
    # Строим сервис с history и свежим recommended_range (чтобы не было auto-recalc побочных эффектов).
    history = _FakeHistory()
    service, _, coins = _build_service(_coin(rr_dt=_dt(0)), _dt(10), history=history)
    result = service.run_check("BTC", persist=False)
    assert result.symbol == "BTC"
    assert coins.updated == []
    assert history.saved == []
