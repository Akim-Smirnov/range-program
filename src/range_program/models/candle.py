"""
Модель свечи (OHLCV).

Файл описывает одну свечу: время и значения open/high/low/close/volume.
Используется в расчётах диапазона и в backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Одна биржевая свеча (OHLCV) в момент `timestamp`."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
