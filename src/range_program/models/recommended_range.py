from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from range_program.models.grid_config import GridConfig


@dataclass(frozen=True)
class RecommendedRange:
    low: float
    high: float
    center: float
    width_pct: float
    calculated_at: datetime
    center_method: str
    width_method: str
    grid_configs: tuple[GridConfig, ...] = ()
