"""
Конфигурация сетки (grid) поверх рекомендованного диапазона.

Файл хранит модель параметров сетки для конкретного режима: количество уровней,
шаг и размер ордера.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridConfig:
    """
    Вариант геометрической сетки поверх уже рассчитанного recommended_range.

    `mode` задаёт режим (например, conservative/balanced/aggressive), а остальные поля
    описывают форму сетки: сколько уровней, шаг и размер ордера.
    """

    mode: str
    grid_count: int
    step_pct: float
    order_size: float
