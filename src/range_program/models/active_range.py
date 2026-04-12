from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ActiveRange:
    low: float
    high: float
    set_at: datetime
    comment: str | None = None
