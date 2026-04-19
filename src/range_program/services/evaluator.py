from __future__ import annotations

from datetime import datetime, timezone

from range_program.config import (
    EVAL_NEAR_EDGE_FRAC,
    EVAL_REPOSITION_CENTER_DIFF_PCT,
    EVAL_STALE_DEVIATION_PCT,
)
from range_program.models.check_result import CheckResult
from range_program.models.coin import Coin


class EvaluatorError(Exception):
    """Ошибка оценки (сообщение для пользователя)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Пороги MVP (доли и проценты)
_NEAR_EDGE_FRAC = EVAL_NEAR_EDGE_FRAC  # 5% ширины диапазона до границы
_STALE_DEVIATION_PCT = EVAL_STALE_DEVIATION_PCT
_REPOSITION_CENTER_DIFF_PCT = EVAL_REPOSITION_CENTER_DIFF_PCT

_RECOMMENDATIONS: dict[str, str] = {
    "OUT_OF_RANGE": "Диапазон больше не актуален — цена вне сетки; нужно переставить сетку.",
    "WARNING": "Диапазон ещё рабочий, но цена близко к границе — стоит наблюдать.",
    "STALE": "Цена заметно ушла от центра активного диапазона; новый расчёт выглядит предпочтительнее.",
    "REPOSITION": "Рекомендуемый центр заметно сместился относительно активного — желательно переставить сетку.",
    "OK": "Текущая сетка в целом приемлема; можно оставить.",
}


def _safe_pct(numer: float, denom: float) -> float:
    if denom == 0.0:
        return 0.0
    return (numer / denom) * 100.0


class Evaluator:
    """Оценка active_range относительно цены и recommended_range (MVP, без backtest)."""

    def evaluate(self, coin: Coin, current_price: float) -> CheckResult:
        if coin.active_range is None:
            raise EvaluatorError(
                "Нет активного диапазона (active_range). Задайте в меню: Coins → «Задать active range»."
            )
        if coin.recommended_range is None:
            raise EvaluatorError(
                "Нет рекомендуемого диапазона (recommended_range). Выполните пересчёт: Range analysis → «Пересчитать диапазон»."
            )

        ar = coin.active_range
        rr = coin.recommended_range
        low, high = float(ar.low), float(ar.high)
        if low >= high:
            raise EvaluatorError("Активный диапазон некорректен: low должно быть строго меньше high.")

        if current_price <= 0:
            raise EvaluatorError("Текущая цена не получена или некорректна.")

        active_center = (low + high) / 2.0
        rec_center = float(rr.center)

        # Метрики (читаемые формулы в комментариях к полям CheckResult)
        distance_to_lower_pct = _safe_pct(current_price - low, low)
        distance_to_upper_pct = _safe_pct(high - current_price, high)
        deviation_from_active_center_pct = _safe_pct(abs(current_price - active_center), active_center)

        inside = low <= current_price <= high
        width = high - low

        status, recommendation = self._pick_status(
            current_price=current_price,
            low=low,
            high=high,
            width=width,
            inside=inside,
            active_center=active_center,
            rec_center=rec_center,
            deviation_pct=deviation_from_active_center_pct,
            distance_to_lower_pct=distance_to_lower_pct,
            distance_to_upper_pct=distance_to_upper_pct,
        )

        if ar.comment:
            recommendation = f"{recommendation} (active_range: {ar.comment})"

        return CheckResult(
            symbol=coin.symbol,
            current_price=float(current_price),
            active_low=low,
            active_high=high,
            active_center=active_center,
            recommended_low=float(rr.low),
            recommended_high=float(rr.high),
            recommended_center=rec_center,
            distance_to_lower_pct=float(distance_to_lower_pct),
            distance_to_upper_pct=float(distance_to_upper_pct),
            deviation_from_active_center_pct=float(deviation_from_active_center_pct),
            status=status,
            recommendation=recommendation,
            checked_at=_utc_now(),
        )

    def _pick_status(
        self,
        *,
        current_price: float,
        low: float,
        high: float,
        width: float,
        inside: bool,
        active_center: float,
        rec_center: float,
        deviation_pct: float,
        distance_to_lower_pct: float,
        distance_to_upper_pct: float,
    ) -> tuple[str, str]:
        """Приоритет: OUT_OF_RANGE > REPOSITION > STALE > WARNING > OK."""

        # 1. OUT_OF_RANGE
        if current_price < low or current_price > high:
            if current_price < low:
                diff = low - current_price
                pct = _safe_pct(diff, low)
                hint = f"Цена ниже low на {diff:g} (≈{pct:.1f}%). Переставьте сетку ниже/сузьте диапазон."
            else:
                diff = current_price - high
                pct = _safe_pct(diff, high)
                hint = f"Цена выше high на {diff:g} (≈{pct:.1f}%). Переставьте сетку выше/расширьте диапазон."
            return "OUT_OF_RANGE", f"{_RECOMMENDATIONS['OUT_OF_RANGE']} {hint}"

        # Цена внутри [low, high] для остальных правил
        assert inside

        # 2. REPOSITION — центр recommended отличается от центра active > 10%
        if active_center > 0:
            center_diff_pct = abs(rec_center - active_center) / active_center * 100.0
            if center_diff_pct > _REPOSITION_CENTER_DIFF_PCT:
                direction = "выше" if rec_center > active_center else "ниже"
                hint = (
                    f"Рекомендуемый центр {direction} активного на ≈{center_diff_pct:.1f}% "
                    f"(active_center={active_center:g}, recommended_center={rec_center:g})."
                )
                return "REPOSITION", f"{_RECOMMENDATIONS['REPOSITION']} {hint}"

        # 3. STALE — отклонение цены от центра active > 12%
        if deviation_pct > _STALE_DEVIATION_PCT:
            hint = f"Отклонение от центра active ≈{deviation_pct:.1f}% (цена={current_price:g}, active_center={active_center:g})."
            return "STALE", f"{_RECOMMENDATIONS['STALE']} {hint}"

        # 4. WARNING — близко к границе (нижние/верхние 5% ширины)
        if width > 0:
            pos = (current_price - low) / width
            if pos < _NEAR_EDGE_FRAC or pos > 1.0 - _NEAR_EDGE_FRAC:
                edge = "нижней" if pos < 0.5 else "верхней"
                dist = distance_to_lower_pct if edge == "нижней" else distance_to_upper_pct
                hint = f"Цена ближе к {edge} границе; запас ≈{dist:.1f}%."
                return "WARNING", f"{_RECOMMENDATIONS['WARNING']} {hint}"

        # 5. OK
        return "OK", _RECOMMENDATIONS["OK"]
