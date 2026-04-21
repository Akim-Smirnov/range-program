"""
Результат проверки монеты (check).

Файл содержит модель данных, которую возвращает сервис проверки: текущая цена, активный
и рекомендуемый диапазоны, метрики отклонения и итоговое сообщение/статус.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CheckResult:
    """
    Итог проверки монеты.

    Содержит:
    - `active_*`: текущий активный диапазон пользователя,
    - `recommended_*`: рассчитанный рекомендуемый диапазон,
    - метрики расстояния/отклонения в процентах,
    - `status` и `recommendation`,
    - `checked_at` (UTC).
    """

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
