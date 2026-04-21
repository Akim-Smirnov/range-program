"""
Backtest "жизни" диапазона на истории.

Файл содержит функцию `run_backtest`, которая симулирует движение цены по историческим
свечам: строит стартовый диапазон, затем оценивает статус (OK/WARNING/STALE/REPOSITION)
до выхода цены за границы.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone

from range_program.models.active_range import ActiveRange
from range_program.models.backtest_result import BacktestResult
from range_program.models.coin import Coin
from range_program.services.evaluator import Evaluator, EvaluatorError
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.range_engine import ATR_PERIOD, EMA_PERIOD, RangeEngine, RangeEngineError
from range_program.services.recalc_service import bars_per_day
from range_program.validation import ValidationError

_MIN_WARMUP = max(EMA_PERIOD, ATR_PERIOD)
_MAX_FETCH = 1000


def _utc_now() -> datetime:
    """Текущее время в UTC (для отметок tested_at)."""
    return datetime.now(timezone.utc)


def run_backtest(
    coin: Coin,
    days: int,
    *,
    market: MarketDataService,
    engine: RangeEngine | None = None,
    evaluator: Evaluator | None = None,
) -> BacktestResult:
    """
    Строит диапазон в стартовой точке после прогрева свечей, затем идёт вперёд по close:
    на каждом шаге пересчитывает recommended через RangeEngine и оценивает через Evaluator.
    """
    if days < 1:
        raise ValidationError("Параметр --days должен быть не меньше 1.")

    eng = engine or RangeEngine()
    ev = evaluator or Evaluator()

    bpd = bars_per_day(coin.timeframe)
    if bpd <= 0:
        raise ValidationError("Не удалось оценить число свечей в день для таймфрейма монеты.")

    forward_bars = max(1, math.ceil(days * bpd))
    required_len = _MIN_WARMUP + forward_bars
    if required_len > _MAX_FETCH:
        raise ValidationError(
            f"Для --days={days} и таймфрейма {coin.timeframe} нужно около {required_len} свечей, "
            f"максимум {_MAX_FETCH}. Уменьшите --days или смените таймфрейм монеты."
        )

    try:
        candles = market.get_ohlcv(coin.symbol, coin.timeframe, required_len, coin=coin)
    except MarketDataError as e:
        raise ValidationError(f"Не удалось загрузить свечи: {e}") from e

    if len(candles) < required_len:
        raise ValidationError(
            f"Недостаточно свечей: нужно {required_len} (прогрев {_MIN_WARMUP} + период {forward_bars}), "
            f"получено {len(candles)}. Увеличьте период или проверьте пару на бирже."
        )

    candles_sorted = sorted(candles, key=lambda c: c.timestamp)
    start_idx = _MIN_WARMUP - 1

    try:
        rr0 = eng.calculate_range(
            coin,
            current_price=float(candles_sorted[start_idx].close),
            candles=candles_sorted[: start_idx + 1],
        )
    except RangeEngineError as e:
        raise ValidationError(f"Не удалось построить диапазон в стартовой точке: {e}") from e

    low0, high0 = float(rr0.low), float(rr0.high)
    active = ActiveRange(
        low=low0,
        high=high0,
        set_at=candles_sorted[start_idx].timestamp,
    )

    ok_count = 0
    warning_count = 0
    stale_count = 0
    reposition_count = 0
    max_dev = 0.0
    hit_upper = False
    hit_lower = False
    lifetime_candles = 0

    end_idx = min(start_idx + forward_bars, len(candles_sorted)) - 1

    for j in range(start_idx, end_idx + 1):
        price = float(candles_sorted[j].close)
        history = candles_sorted[: j + 1]

        try:
            rr_j = eng.calculate_range(coin, current_price=price, candles=history)
        except RangeEngineError as e:
            raise ValidationError(f"Ошибка RangeEngine на свече {j}: {e}") from e

        coin_step = replace(coin, active_range=active, recommended_range=rr_j)

        try:
            chk = ev.evaluate(coin_step, price)
        except EvaluatorError as e:
            raise ValidationError(f"Ошибка Evaluator на свече {j}: {e}") from e

        dev = abs(float(chk.deviation_from_active_center_pct))
        if dev > max_dev:
            max_dev = dev

        st = chk.status
        if st == "OUT_OF_RANGE":
            if price > high0:
                hit_upper = True
            elif price < low0:
                hit_lower = True
            lifetime_candles = j - start_idx
            break

        if st == "OK":
            ok_count += 1
        elif st == "WARNING":
            warning_count += 1
        elif st == "STALE":
            stale_count += 1
        elif st == "REPOSITION":
            reposition_count += 1

        lifetime_candles = j - start_idx + 1

    if not hit_upper and not hit_lower:
        lifetime_candles = end_idx - start_idx + 1

    lifetime_days = lifetime_candles / bpd if bpd else 0.0

    summary = _build_summary(
        hit_upper=hit_upper,
        hit_lower=hit_lower,
        ok_count=ok_count,
        warning_count=warning_count,
        stale_count=stale_count,
        reposition_count=reposition_count,
        max_dev=max_dev,
    )

    return BacktestResult(
        symbol=coin.symbol,
        start_price=float(candles_sorted[start_idx].close),
        range_low=low0,
        range_high=high0,
        lifetime_candles=lifetime_candles,
        lifetime_days=lifetime_days,
        hit_upper=hit_upper,
        hit_lower=hit_lower,
        max_deviation_pct=max_dev,
        stale_count=stale_count,
        ok_count=ok_count,
        warning_count=warning_count,
        reposition_count=reposition_count,
        result_summary=summary,
        tested_at=_utc_now(),
    )


def _build_summary(
    *,
    hit_upper: bool,
    hit_lower: bool,
    ok_count: int,
    warning_count: int,
    stale_count: int,
    reposition_count: int,
    max_dev: float,
) -> str:
    """Собрать короткое текстовое резюме результата backtest (для отображения пользователю)."""
    parts: list[str] = []
    if not hit_upper and not hit_lower:
        parts.append("Price stayed inside the active range for the whole simulated window.")
    elif hit_lower and not hit_upper:
        parts.append("Lower bound was hit first; the grid would need a reset from that side.")
    elif hit_upper and not hit_lower:
        parts.append("Upper bound was hit first; the grid would need a reset from that side.")
    else:
        parts.append("Range boundaries were touched; review OHLC if this looks unexpected.")

    total_sig = ok_count + warning_count + stale_count + reposition_count
    if total_sig > 0 and ok_count >= total_sig // 2:
        parts.append("Most steps were OK relative to the fixed range.")
    elif stale_count > ok_count:
        parts.append("STALE dominated: price often far from the active center before exit or window end.")
    if reposition_count > 0:
        parts.append(f"REPOSITION suggested {reposition_count} time(s) (recommended center drifted).")

    parts.append(f"Max deviation from active center: {max_dev:.1f}%.")
    return " ".join(parts)
