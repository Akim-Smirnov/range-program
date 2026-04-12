from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridConfig:
    """Вариант геометрической сетки поверх уже рассчитанного recommended_range."""

    mode: str
    grid_count: int
    step_pct: float
    order_size: float
