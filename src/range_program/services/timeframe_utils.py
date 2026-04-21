"""
Утилиты для таймфреймов.

Файл содержит функцию, которая оценивает количество свечей в сутки по строке таймфрейма
в формате ccxt (например, 1m, 4h, 1d).
"""

from __future__ import annotations

import re


def bars_per_day(timeframe: str) -> float:
    """Грубая оценка числа свечей в сутки для таймфрейма ccxt (1m, 4h, 1d, ...)."""
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
