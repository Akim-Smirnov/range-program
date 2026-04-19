from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ActiveRange:
    """
    Активный диапазон (как стоит бот) для конкретной монеты.

    - low/high: границы сетки пользователя.
    - set_at: время установки диапазона (UTC).
    - comment: опциональный комментарий (например “переставил после новости”).
    """

    low: float
    high: float
    set_at: datetime
    comment: str | None = None
