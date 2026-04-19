"""
RecalcService — обновление рекомендованного диапазона (recommended_range) по рынку.

Этот модуль выполняет “оркестрацию” recalc:
- Берёт монету из локального хранилища (`CoinService`).
- Определяет, сколько свечей нужно запросить у биржи, исходя из `timeframe`,
  `lookback_days` и минимальных требований выбранных методов (center/width).
- Через `MarketDataService` находит рабочий рынок (биржа + пара), загружает свечи
  и текущую цену (только чтение, без торговли).
- Передаёт данные в `RangeEngine` для расчёта `RecommendedRange`, а также таблиц
  сравнения методов центра и ширины (для вывода в CLI/меню).
- По флагу `save` может:
  - сохранить `recommended_range` (и кэш рынка `resolved_*`) обратно в монету,
  - либо ничего не сохранять (режим анализа/подбора параметров).

Также поддерживает override-параметры (`timeframe`, `lookback_days`,
`center_method`, `width_method`) — чтобы “примерять” настройки без ручного
редактирования `data/coins.json`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from range_program.models.coin import Coin
from range_program.models.recommended_range import RecommendedRange
from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.range_engine import RangeEngine, RangeEngineError, min_candles_required
from range_program.services.timeframe_utils import bars_per_day as _bars_per_day
from range_program.validation import (
    ValidationError,
    validate_center_method,
    validate_lookback_days,
    validate_timeframe,
    validate_width_method,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def bars_per_day(timeframe: str) -> float:
    """Оценка числа свечей в сутки для таймфрейма (как в ccxt: 1m, 4h, 1d, …)."""
    return _bars_per_day(timeframe)


def estimate_candle_limit(timeframe: str, lookback_days: int) -> int:
    """Перевод lookback_days в лимит свечей (с запасом), с ограничением API.

    Важно: для крупных таймфреймов (например, 1d) фиксированный минимум 80
    может быть избыточным, поэтому минимум делаем “адаптивным”: достаточно
    запросить столько свечей, сколько нужно по lookback, но не меньше, чем
    требуется выбранным методам расчёта (center/width).
    """
    return estimate_candle_limit_with_min(timeframe, lookback_days, min_required=1)


def estimate_candle_limit_with_min(timeframe: str, lookback_days: int, *, min_required: int) -> int:
    """Как estimate_candle_limit, но с явным минимумом нужных свечей."""
    bpd = _bars_per_day(timeframe)
    buffer = 5
    raw = max(1, int(lookback_days * bpd) + buffer)
    need = max(1, int(min_required))
    return min(1000, max(raw, need + buffer))


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

    def recalc(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
        lookback_days: int | None = None,
        center_method: str | None = None,
        width_method: str | None = None,
        save: bool = True,
    ) -> RecalcOutcome:
        sym = Coin.normalize_symbol(symbol)
        coin = self._coins.get_coin(sym)
        if coin is None:
            raise ValidationError(f"Монета {sym} не найдена в хранилище.")

        if timeframe is not None:
            validate_timeframe(timeframe)
        if lookback_days is not None:
            validate_lookback_days(int(lookback_days))
        if center_method is not None:
            validate_center_method(center_method)
        if width_method is not None:
            validate_width_method(width_method)

        working = coin.with_settings(
            timeframe=timeframe,
            lookback_days=lookback_days,
            center_method=center_method,
            width_method=width_method,
        )

        need = min_candles_required(working.center_method, working.width_method)
        limit = estimate_candle_limit_with_min(working.timeframe, working.lookback_days, min_required=need)

        match = None
        try:
            match = self._market.resolve_market(coin)
            candles = self._market.fetch_ohlcv_with_match(match, working.timeframe, limit)
            pq = self._market.fetch_price_quote_with_match(match)
            current_price = pq.price
        except MarketDataError as e:
            ctx = (
                f"symbol={sym}, timeframe={working.timeframe!r}, lookback_days={working.lookback_days}, "
                f"limit={limit}"
            )
            if match is not None:
                ctx += f", exchange={match.exchange!r}, pair={match.symbol_pair!r}"
            raise MarketDataError(f"{e} ({ctx})") from e

        got = len(candles)
        if got < need:
            m = f"{match.exchange}:{match.symbol_pair}" if match is not None else "(market not resolved)"
            raise ValidationError(
                "Слишком мало свечей для расчёта recommended_range: "
                f"получено {got}, нужно минимум {need} "
                f"(symbol={sym}, market={m}, timeframe={working.timeframe!r}, "
                f"lookback_days={working.lookback_days}, limit={limit}, "
                f"center_method={working.center_method!r}, width_method={working.width_method!r})."
            )

        try:
            rr = self._engine.calculate_range(working, current_price=current_price, candles=candles)
            center_comparison = self._engine.compare_center_methods_for_recalc(
                working, current_price=current_price, candles=candles
            )
            width_comparison = self._engine.compare_width_methods_for_recalc(
                working, current_price=current_price, candles=candles
            )
        except RangeEngineError as e:
            ctx = (
                f"symbol={sym}, timeframe={working.timeframe!r}, lookback_days={working.lookback_days}, "
                f"limit={limit}, candles={got}, center_method={working.center_method!r}, "
                f"width_method={working.width_method!r}"
            )
            if match is not None:
                ctx += f", exchange={match.exchange!r}, pair={match.symbol_pair!r}"
            raise RangeEngineError(f"{e} ({ctx})") from e

        if save:
            now = _utc_now()
            updated = replace(
                coin,
                recommended_range=rr,
                updated_at=now,
                resolved_exchange=match.exchange,
                resolved_symbol_pair=match.symbol_pair,
                resolved_at=now,
            )
            if timeframe is not None:
                updated = replace(updated, timeframe=working.timeframe)
            if lookback_days is not None:
                updated = replace(updated, lookback_days=working.lookback_days)
            if center_method is not None:
                updated = replace(updated, center_method=working.center_method)
            if width_method is not None:
                updated = replace(updated, width_method=working.width_method)

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
