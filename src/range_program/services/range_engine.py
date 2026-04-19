from __future__ import annotations

import statistics
from dataclasses import replace
from datetime import datetime, timezone
from typing import Sequence

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.models.defaults import ALLOWED_CENTER_METHODS, ALLOWED_MODES, ALLOWED_WIDTH_METHODS
from range_program.models.grid_config import GridConfig
from range_program.models.recommended_range import RecommendedRange


class RangeEngineError(Exception):
    """Ошибка расчёта диапазона (сообщение для пользователя)."""


EMA_PERIOD = 20
SMA_PERIOD = 20
MEDIAN_PERIOD = 20
MIDPOINT_PERIOD = 20
DONCHIAN_PERIOD = 20
ATR_PERIOD = 14
STD_PERIOD = 20
HISTORICAL_RANGE_PERIOD = 20

# Порядок строк при recalc: сравнение всех методов центра (без смены настроек монеты).
RECALC_CENTER_COMPARISON_ORDER: tuple[str, ...] = (
    "price",
    "ema",
    "sma",
    "median",
    "midpoint",
    "donchian",
)

# Порядок строк при recalc: сравнение всех методов ширины (без смены center_method монеты).
RECALC_WIDTH_COMPARISON_ORDER: tuple[str, ...] = (
    "atr",
    "std",
    "donchian",
    "historical_range",
)

_ATR_MULT: dict[str, float] = {
    "conservative": 6.0,
    "balanced": 4.0,
    "aggressive": 3.0,
}

# Множители к std(close) для half_width (отдельно от ATR).
_STD_MULT: dict[str, float] = {
    "conservative": 3.0,
    "balanced": 2.2,
    "aggressive": 1.6,
}

_MIN_WIDTH_PCT: dict[str, float] = {
    "conservative": 16.0,
    "balanced": 12.0,
    "aggressive": 8.0,
}

_MAX_WIDTH_PCT: dict[str, float] = {
    "conservative": 40.0,
    "balanced": 30.0,
    "aggressive": 20.0,
}

# Геометрическая сетка поверх recommended_range: профили по плотности; не путать с coin.mode (ширина ATR).
_GRID_STEP_PCT: tuple[tuple[str, float], ...] = (
    ("aggressive", 0.5),
    ("balanced", 0.8),
    ("conservative", 1.4),
)
_MIN_GRIDS = 10
_MAX_GRIDS = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sorted_candles(candles: Sequence[Candle]) -> list[Candle]:
    return sorted(candles, key=lambda c: c.timestamp)


def _min_candles_for_center_only(center_method: str) -> int:
    """Минимум свечей только для расчёта центра (без учёта width_method)."""
    cm = center_method.strip().lower()
    if cm == "price":
        return 0
    period_by_method = {
        "ema": EMA_PERIOD,
        "sma": SMA_PERIOD,
        "median": MEDIAN_PERIOD,
        "midpoint": MIDPOINT_PERIOD,
        "donchian": DONCHIAN_PERIOD,
    }
    return period_by_method.get(cm, 0)


def _min_candles_for_width_method(width_method: str) -> int:
    wm = width_method.strip().lower()
    if wm == "atr":
        return ATR_PERIOD
    if wm == "std":
        return STD_PERIOD
    if wm == "donchian":
        return DONCHIAN_PERIOD
    if wm == "historical_range":
        return HISTORICAL_RANGE_PERIOD
    return 0


def _min_candles_required(center_method: str, width_method: str) -> int:
    return max(_min_candles_for_center_only(center_method), _min_candles_for_width_method(width_method), 1)


def min_candles_required(center_method: str, width_method: str) -> int:
    """Публичная функция: минимум свечей для пары методов (center + width)."""
    return _min_candles_required(center_method, width_method)


def _ema_last(closes: list[float], period: int) -> float:
    if len(closes) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для EMA({period}): нужно хотя бы {period}, есть {len(closes)}."
        )
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1.0 - k)
    return ema


def _calculate_center_sma(closes: list[float], period: int) -> float:
    if len(closes) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для SMA({period}): нужно хотя бы {period}, есть {len(closes)}."
        )
    window = closes[-period:]
    return sum(window) / float(period)


def _calculate_center_median(closes: list[float], period: int) -> float:
    if len(closes) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для median по {period} закрытиям: нужно хотя бы {period}, есть {len(closes)}."
        )
    window = closes[-period:]
    return float(statistics.median(window))


def _calculate_center_midpoint(candles: list[Candle], period: int) -> float:
    """Центр = (max high + min low) / 2 по последним period свечам."""
    if len(candles) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для midpoint({period}): нужно хотя бы {period}, есть {len(candles)}."
        )
    w = candles[-period:]
    hi = max(bar.high for bar in w)
    lo = min(bar.low for bar in w)
    return (hi + lo) / 2.0


def _calculate_center_donchian(candles: list[Candle], period: int) -> float:
    """Центр канала Дончиана: (highest_high + lowest_low) / 2; в MVP окно как у midpoint."""
    if len(candles) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для donchian({period}): нужно хотя бы {period}, есть {len(candles)}."
        )
    w = candles[-period:]
    hi = max(bar.high for bar in w)
    lo = min(bar.low for bar in w)
    return (hi + lo) / 2.0


def _resolve_center(
    center_method: str,
    *,
    current_price: float,
    series: list[Candle],
    closes: list[float],
) -> float:
    cm = center_method.strip().lower()
    if cm == "price":
        return float(current_price)
    if cm == "ema":
        return float(_ema_last(closes, EMA_PERIOD))
    if cm == "sma":
        return float(_calculate_center_sma(closes, SMA_PERIOD))
    if cm == "median":
        return float(_calculate_center_median(closes, MEDIAN_PERIOD))
    if cm == "midpoint":
        return float(_calculate_center_midpoint(series, MIDPOINT_PERIOD))
    if cm == "donchian":
        return float(_calculate_center_donchian(series, DONCHIAN_PERIOD))
    raise RangeEngineError(f"center_method «{center_method}» не поддерживается (ожидалось одно из: {sorted(ALLOWED_CENTER_METHODS)}).")


def _true_ranges(candles: list[Candle]) -> list[float]:
    tr: list[float] = []
    for i, bar in enumerate(candles):
        h, l = bar.high, bar.low
        if i == 0:
            tr.append(h - l)
        else:
            pc = candles[i - 1].close
            tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def _atr_wilder(candles: list[Candle], period: int) -> float:
    if len(candles) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для ATR({period}): нужно хотя бы {period}, есть {len(candles)}."
        )
    tr = _true_ranges(candles)
    if len(tr) < period:
        raise RangeEngineError("Не удалось посчитать true range для ATR.")
    atr = sum(tr[:period]) / period
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
    return atr


def _calculate_half_width_atr(candles: list[Candle], mode: str) -> float:
    atr_val = _atr_wilder(candles, ATR_PERIOD)
    return float(atr_val) * _ATR_MULT[mode]


def _calculate_half_width_std(closes: list[float], mode: str) -> float:
    if len(closes) < STD_PERIOD:
        raise RangeEngineError(
            f"Недостаточно свечей для std({STD_PERIOD}): нужно хотя бы {STD_PERIOD}, есть {len(closes)}."
        )
    window = closes[-STD_PERIOD:]
    if len(window) < 2:
        raise RangeEngineError("Недостаточно точек для стандартного отклонения.")
    sd = statistics.pstdev(window)
    mult = _STD_MULT[mode]
    return float(sd) * mult


def _calculate_half_width_channel(candles: list[Candle], period: int, *, label: str) -> float:
    """Полуширина (max_high - min_low) / 2 по окну; для donchian и historical_range (MVP — одна формула)."""
    if len(candles) < period:
        raise RangeEngineError(
            f"Недостаточно свечей для {label}({period}): нужно хотя бы {period}, есть {len(candles)}."
        )
    w = candles[-period:]
    hi = max(bar.high for bar in w)
    lo = min(bar.low for bar in w)
    full_w = hi - lo
    if full_w <= 0:
        raise RangeEngineError(f"Нулевая или отрицательная ширина канала ({label}).")
    return full_w / 2.0


def _calculate_half_width_donchian(candles: list[Candle]) -> float:
    return _calculate_half_width_channel(candles, DONCHIAN_PERIOD, label="width_donchian")


def _calculate_half_width_historical_range(candles: list[Candle]) -> float:
    return _calculate_half_width_channel(candles, HISTORICAL_RANGE_PERIOD, label="historical_range")


def _resolve_half_width(
    width_method: str,
    *,
    series: list[Candle],
    closes: list[float],
    mode: str,
) -> float:
    wm = width_method.strip().lower()
    if wm == "atr":
        return _calculate_half_width_atr(series, mode)
    if wm == "std":
        return _calculate_half_width_std(closes, mode)
    if wm == "donchian":
        return _calculate_half_width_donchian(series)
    if wm == "historical_range":
        return _calculate_half_width_historical_range(series)
    raise RangeEngineError(
        f"width_method «{width_method}» не поддерживается (ожидалось одно из: {', '.join(sorted(ALLOWED_WIDTH_METHODS))})."
    )


def compute_geometric_grid_configs(width_pct: float, capital: float) -> tuple[GridConfig, ...]:
    """
    Три варианта геометрической сетки: step фиксирован по профилю,
    grid_count = clamp(round(width_pct / step_pct), 10, 120), order_size = capital / grid_count.
    """
    if width_pct <= 0:
        raise RangeEngineError("Ширина диапазона (width_pct) должна быть положительной.")
    if capital <= 0:
        raise RangeEngineError("Капитал (capital) должен быть положительным.")

    out: list[GridConfig] = []
    for profile, step_raw in _GRID_STEP_PCT:
        step_pct = round(float(step_raw), 2)
        if step_pct <= 0:
            raise RangeEngineError("Внутренняя ошибка: step_pct должен быть > 0.")
        raw_count = round(width_pct / step_pct)
        grid_count = int(max(_MIN_GRIDS, min(_MAX_GRIDS, raw_count)))
        order_size = round(capital / grid_count, 2)
        out.append(
            GridConfig(
                mode=profile,
                grid_count=grid_count,
                step_pct=step_pct,
                order_size=order_size,
            )
        )
    return tuple(out)


def _clamp_half_width(center: float, half_width: float, mode: str) -> float:
    """Симметричный half-width после ограничения полной ширины в %% от центра."""
    if center <= 0:
        raise RangeEngineError("Центр диапазона должен быть положительным (некорректная цена).")
    min_pct = _MIN_WIDTH_PCT[mode]
    max_pct = _MAX_WIDTH_PCT[mode]
    full_w = 2.0 * half_width
    width_pct = (full_w / center) * 100.0
    if width_pct < min_pct:
        return center * (min_pct / 100.0) / 2.0
    if width_pct > max_pct:
        return center * (max_pct / 100.0) / 2.0
    return half_width


class RangeEngine:
    """Движок: несколько center_method и width_method (atr, std, donchian, historical_range), clamp по %."""

    def calculate_range(
        self,
        coin: Coin,
        *,
        current_price: float,
        candles: Sequence[Candle],
    ) -> RecommendedRange:
        cm = coin.center_method.strip().lower()
        wm = coin.width_method.strip().lower()
        mode = coin.mode.strip().lower()

        if wm not in ALLOWED_WIDTH_METHODS:
            raise RangeEngineError(
                f"width_method «{coin.width_method}» не поддерживается "
                f"(ожидалось одно из: {', '.join(sorted(ALLOWED_WIDTH_METHODS))})."
            )
        if cm not in ALLOWED_CENTER_METHODS:
            raise RangeEngineError(
                f"center_method «{coin.center_method}» не поддерживается "
                f"(ожидалось одно из: {', '.join(sorted(ALLOWED_CENTER_METHODS))})."
            )
        if mode not in ALLOWED_MODES:
            raise RangeEngineError(f"Неизвестный mode «{coin.mode}».")

        if current_price <= 0:
            raise RangeEngineError("Текущая цена не получена или некорректна.")

        series = _sorted_candles(candles)
        if not series:
            raise RangeEngineError("Нет свечей для расчёта диапазона.")

        need = _min_candles_required(cm, wm)
        if len(series) < need:
            raise RangeEngineError(
                f"Слишком мало свечей для расчёта: минимум {need} "
                f"(center_method={cm!r}, width_method={wm!r}), есть {len(series)}."
            )

        closes = [c.close for c in series]
        center = _resolve_center(cm, current_price=current_price, series=series, closes=closes)
        if center <= 0:
            raise RangeEngineError("Центр диапазона получился неположительным (проверьте данные свечей).")

        half_width = _resolve_half_width(wm, series=series, closes=closes, mode=mode)
        if half_width <= 0:
            raise RangeEngineError("Полуширина диапазона получилась неположительной (проверьте width_method и данные).")

        half_width = _clamp_half_width(center, half_width, mode)

        low = center - half_width
        high = center + half_width
        if low >= high:
            raise RangeEngineError("После ограничений границы диапазона некорректны (low >= high).")

        width_pct = ((high - low) / center) * 100.0 if center else 0.0
        if width_pct <= 0:
            raise RangeEngineError("Ширина диапазона получилась неположительной (проверьте цены).")

        grid_cfgs: tuple[GridConfig, ...] = ()
        cap = coin.capital
        if cap is not None:
            if cap <= 0:
                raise RangeEngineError("Капитал (capital) должен быть положительным, либо не задавайте его.")
            grid_cfgs = compute_geometric_grid_configs(width_pct, cap)

        return RecommendedRange(
            low=low,
            high=high,
            center=center,
            width_pct=width_pct,
            calculated_at=_utc_now(),
            center_method=cm,
            width_method=wm,
            grid_configs=grid_cfgs,
        )

    def compare_center_methods_for_recalc(
        self,
        coin: Coin,
        *,
        current_price: float,
        candles: Sequence[Candle],
    ) -> tuple[tuple[str, RecommendedRange], ...]:
        """
        Считает recommended_range для каждого center_method из RECALC_CENTER_COMPARISON_ORDER
        при тех же свечах и width_method монеты. Капитал не учитывается (без grid_configs).
        """
        base = replace(coin, capital=None)
        out: list[tuple[str, RecommendedRange]] = []
        for m in RECALC_CENTER_COMPARISON_ORDER:
            c = replace(base, center_method=m)
            rr = self.calculate_range(c, current_price=current_price, candles=candles)
            out.append((m, rr))
        return tuple(out)

    def compare_width_methods_for_recalc(
        self,
        coin: Coin,
        *,
        current_price: float,
        candles: Sequence[Candle],
    ) -> tuple[tuple[str, RecommendedRange], ...]:
        """
        Считает recommended_range для каждого width_method из RECALC_WIDTH_COMPARISON_ORDER
        при том же center_method монеты. Капитал не учитывается (без grid_configs).
        """
        base = replace(coin, capital=None)
        out: list[tuple[str, RecommendedRange]] = []
        for w in RECALC_WIDTH_COMPARISON_ORDER:
            c = replace(base, width_method=w)
            rr = self.calculate_range(c, current_price=current_price, candles=candles)
            out.append((w, rr))
        return tuple(out)
