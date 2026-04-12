from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BacktestResult:
    """Результат простого backtest «жизни» диапазона на исторических свечах (MVP)."""

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
