"""
Правила "свежести" рекомендованного диапазона (recommended_range).

Файл определяет TTL (сколько времени recommended_range считается актуальным) в зависимости
от timeframe и функцию проверки устаревания.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from range_program.services.timeframe_utils import bars_per_day


_DEFAULT_RECOMMENDED_RANGE_TTL = timedelta(hours=24)
_RECOMMENDED_RANGE_TTL_BY_TIMEFRAME: dict[str, timedelta] = {
    "1h": timedelta(hours=12),
    "4h": timedelta(hours=24),
    "1d": timedelta(hours=72),
}


def _as_utc(dt: datetime) -> datetime:
    """Нормализовать datetime к UTC; naive значения трактуются как UTC по соглашению проекта."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recommended_range_ttl_for_timeframe(timeframe: str) -> timedelta:
    """
    Вернуть TTL для recommended_range.

    Для 1h/4h/1d используются явные правила.
    Для остальных таймфреймов fallback держит диапазон "свежим" примерно 6 свечей,
    используя `bars_per_day` для оценки.
    """
    tf = timeframe.strip().lower()
    explicit = _RECOMMENDED_RANGE_TTL_BY_TIMEFRAME.get(tf)
    if explicit is not None:
        return explicit
    if re.match(r"^\d+[mhdw]$", tf) is None:
        return _DEFAULT_RECOMMENDED_RANGE_TTL
    bpd = bars_per_day(tf)
    if bpd <= 0:
        return _DEFAULT_RECOMMENDED_RANGE_TTL
    fallback_hours = 24.0 * 6.0 / bpd
    return timedelta(hours=fallback_hours)


def is_recommended_range_stale(*, calculated_at: datetime, timeframe: str, now_utc: datetime) -> bool:
    """True если calculated_at + TTL <= now_utc (граница считается устаревшей по дизайну)."""
    calculated_at_utc = _as_utc(calculated_at)
    now_utc_normalized = _as_utc(now_utc)
    return now_utc_normalized >= calculated_at_utc + recommended_range_ttl_for_timeframe(timeframe)
