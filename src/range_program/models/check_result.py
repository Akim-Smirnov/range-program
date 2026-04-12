from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CheckResult:
    symbol: str
    current_price: float
    active_low: float
    active_high: float
    active_center: float
    recommended_low: float
    recommended_high: float
    recommended_center: float
    distance_to_lower_pct: float
    distance_to_upper_pct: float
    deviation_from_active_center_pct: float
    status: str
    recommendation: str
    checked_at: datetime
