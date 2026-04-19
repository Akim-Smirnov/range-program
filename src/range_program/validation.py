"""
Валидация входных данных (доменный слой).

Этот модуль содержит “человеческие” проверки параметров, которые пользователь
задаёт через CLI/меню или которые хранятся в локальных данных.

Зачем это нужно:
- раньше ловить некорректные значения (понятная ошибка вместо странного поведения),
- держать единые правила в одном месте,
- возвращать сообщения ошибок на языке пользователя.
"""

from __future__ import annotations

import re

from range_program.models.defaults import ALLOWED_CENTER_METHODS, ALLOWED_MODES, ALLOWED_WIDTH_METHODS


class ValidationError(Exception):
    """Ошибка проверки входных данных (доменная)."""


def validate_mode(mode: str) -> None:
    """Проверяет, что `mode` входит в список допустимых режимов."""
    m = mode.strip().lower()
    if m not in ALLOWED_MODES:
        allowed = ", ".join(sorted(ALLOWED_MODES))
        raise ValidationError(f"mode должен быть одним из: {allowed}")


def validate_center_method(center_method: str) -> None:
    """Проверяет, что `center_method` поддерживается RangeEngine."""
    cm = center_method.strip().lower()
    if cm not in ALLOWED_CENTER_METHODS:
        allowed = ", ".join(sorted(ALLOWED_CENTER_METHODS))
        raise ValidationError(f"center_method должен быть одним из: {allowed}")


def validate_width_method(width_method: str) -> None:
    """Проверяет, что `width_method` поддерживается RangeEngine."""
    wm = width_method.strip().lower()
    if wm not in ALLOWED_WIDTH_METHODS:
        allowed = ", ".join(sorted(ALLOWED_WIDTH_METHODS))
        raise ValidationError(f"width_method должен быть одним из: {allowed}")


_TIMEFRAME_RE = re.compile(r"^(\d+)([mhdw])$")


def validate_timeframe(timeframe: str) -> None:
    """Проверяет формат таймфрейма свечей (как в ccxt): `<число><m|h|d|w>`."""
    tf = timeframe.strip().lower()
    m = _TIMEFRAME_RE.match(tf)
    if not m:
        raise ValidationError("timeframe должен быть в формате <число><m|h|d|w>, например '4h' или '1d'.")
    n = int(m.group(1))
    if n < 1:
        raise ValidationError("timeframe должен начинаться с числа >= 1, например '1h'.")


def validate_lookback_days(lookback_days: int) -> None:
    """Проверяет глубину истории в днях (lookback_days): должна быть >= 1 и разумной."""
    n = int(lookback_days)
    if n < 1:
        raise ValidationError("lookback_days должен быть >= 1.")
    # “Разумный” верхний предел: технически можно больше, но это почти всегда
    # бесполезно из-за лимитов свечей API и сильно замедляет работу.
    if n > 3650:
        raise ValidationError("lookback_days слишком большой (максимум 3650).")


def validate_range_bounds(low: float, high: float) -> None:
    """Проверяет, что границы диапазона корректны (low < high)."""
    if low >= high:
        raise ValidationError(f"Некорректные границы диапазона: low={low:g} должен быть меньше high={high:g}.")


def validate_capital(capital: float | None) -> None:
    """Капитал по монете: либо не задан, либо строго положительный."""
    if capital is None:
        return
    if capital <= 0:
        raise ValidationError("capital должен быть положительным")
