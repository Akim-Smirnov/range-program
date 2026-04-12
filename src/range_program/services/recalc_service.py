from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from range_program.models.coin import Coin
from range_program.models.recommended_range import RecommendedRange
from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.range_engine import RangeEngine, RangeEngineError
from range_program.validation import ValidationError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bars_per_day(timeframe: str) -> float:
    """Грубая оценка числа свечей в сутки по строке ccxt (1m, 4h, 1d, ...)."""
    tf = timeframe.strip().lower()
    m = re.match(r"^(\d+)([mhdw])$", tf)
    if not m:
        return 24.0
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return (24.0 * 60.0) / n if n else 24.0
    if unit == "h":
        return 24.0 / n if n else 24.0
    if unit == "d":
        return 1.0 / n if n else 1.0
    if unit == "w":
        return 1.0 / (7.0 * n) if n else 1.0 / 7.0
    return 24.0


def bars_per_day(timeframe: str) -> float:
    """Оценка числа свечей в сутки для таймфрейма (как в ccxt: 1m, 4h, 1d, …)."""
    return _bars_per_day(timeframe)


def estimate_candle_limit(timeframe: str, lookback_days: int) -> int:
    """Перевод lookback_days в лимит свечей (с запасом), с ограничением API."""
    bpd = _bars_per_day(timeframe)
    raw = int(lookback_days * bpd) + 5
    return max(80, min(1000, raw))


@dataclass(frozen=True)
class RecalcOutcome:
    """Итог recalc: сохранённый recommended_range и таблицы сравнения center_method и width_method."""

    symbol: str
    mode: str
    current_price: float
    recommended: RecommendedRange
    center_comparison: tuple[tuple[str, RecommendedRange], ...]
    width_comparison: tuple[tuple[str, RecommendedRange], ...]


class RecalcService:
    """Загрузка данных + RangeEngine + сохранение recommended_range (без логики расчёта в CLI)."""

    def __init__(
        self,
        coins: CoinService,
        market: MarketDataService,
        engine: RangeEngine | None = None,
    ) -> None:
        self._coins = coins
        self._market = market
        self._engine = engine or RangeEngine()

    def recalc(self, symbol: str) -> RecalcOutcome:
        sym = Coin.normalize_symbol(symbol)
        coin = self._coins.get_coin(sym)
        if coin is None:
            raise ValidationError(f"Монета {sym} не найдена в хранилище.")

        limit = estimate_candle_limit(coin.timeframe, coin.lookback_days)
        try:
            match = self._market.resolve_market(coin)
            candles = self._market.fetch_ohlcv_with_match(match, coin.timeframe, limit)
            pq = self._market.fetch_price_quote_with_match(match)
            current_price = pq.price
        except MarketDataError:
            raise

        try:
            rr = self._engine.calculate_range(coin, current_price=current_price, candles=candles)
            center_comparison = self._engine.compare_center_methods_for_recalc(
                coin, current_price=current_price, candles=candles
            )
            width_comparison = self._engine.compare_width_methods_for_recalc(
                coin, current_price=current_price, candles=candles
            )
        except RangeEngineError:
            raise

        now = _utc_now()
        updated = replace(
            coin,
            recommended_range=rr,
            updated_at=now,
            resolved_exchange=match.exchange,
            resolved_symbol_pair=match.symbol_pair,
            resolved_at=now,
        )
        if not self._coins.update_coin(updated):
            raise ValidationError(f"Не удалось сохранить монету {coin.symbol}.")

        return RecalcOutcome(
            symbol=coin.symbol,
            mode=coin.mode,
            current_price=float(current_price),
            recommended=rr,
            center_comparison=center_comparison,
            width_comparison=width_comparison,
        )
