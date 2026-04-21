"""
Рекомендованный диапазон для монеты.

Файл содержит модель рассчитанного диапазона (low/high/center) и метаданные расчёта:
когда он был получен, какими методами считались центр/ширина, и варианты сетки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from range_program.models.grid_config import GridConfig


@dataclass(frozen=True)
class RecommendedRange:
    """
    Рекомендованный диапазон, рассчитанный RangeEngine/RecalcService.

    `grid_configs` может хранить варианты сетки для разных режимов.
    """

    low: float
    high: float
    center: float
    width_pct: float
    calculated_at: datetime
    center_method: str
    width_method: str
    grid_configs: tuple[GridConfig, ...] = ()
