"""
Результат backtest "жизни" диапазона.

Файл содержит модель данных, которую возвращает backtest: параметры теста, длительность
жизни диапазона, касания границ и сводные счетчики/итог.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BacktestResult:
    """
    Результат простого backtest "жизни" диапазона на исторических свечах (MVP).

    Поля сгруппированы как:
    - входные параметры теста (symbol/start_price/range_*),
    - длительность (lifetime_*),
    - события (hit_upper/hit_lower),
    - качество (ok/warning/stale и reposition_count),
    - текстовый итог (result_summary) и время теста (tested_at).
    """

    symbol: str
    start_price: float
    range_low: float
    range_high: float
    lifetime_candles: int
    lifetime_days: float
    hit_upper: bool
    hit_lower: bool
    max_deviation_pct: float
    stale_count: int
    ok_count: int
    warning_count: int
    reposition_count: int
    result_summary: str
    tested_at: datetime
