from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.models.defaults import ALLOWED_MODES
from range_program.models.grid_config import GridConfig
from range_program.models.recommended_range import RecommendedRange


class RangeEngineError(Exception):
    """Ошибка расчёта диапазона (сообщение для пользователя)."""


EMA_PERIOD = 20
ATR_PERIOD = 14

_ATR_MULT: dict[str, float] = {
    "conservative": 6.0,
    "balanced": 4.0,
    "aggressive": 3.0,
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
    """Первый MVP-движок: центр (price/EMA20), ширина ATR14 * множитель режима, clamp по %."""

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

        if wm != "atr":
            raise RangeEngineError(f"width_method «{coin.width_method}» не поддерживается (нужен atr).")
        if cm not in ("price", "ema"):
            raise RangeEngineError(f"center_method «{coin.center_method}» не поддерживается (нужны price или ema).")
        if mode not in ALLOWED_MODES:
            raise RangeEngineError(f"Неизвестный mode «{coin.mode}».")

        if current_price <= 0:
            raise RangeEngineError("Текущая цена не получена или некорректна.")

        series = _sorted_candles(candles)
        if len(series) < max(EMA_PERIOD, ATR_PERIOD):
            raise RangeEngineError(
                f"Слишком мало свечей для расчёта: нужно минимум {max(EMA_PERIOD, ATR_PERIOD)}, есть {len(series)}."
            )

        closes = [c.close for c in series]
        if cm == "price":
            center = float(current_price)
        else:
            center = float(_ema_last(closes, EMA_PERIOD))

        atr_val = _atr_wilder(series, ATR_PERIOD)
        mult = _ATR_MULT[mode]
        half_width = float(atr_val) * mult

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
