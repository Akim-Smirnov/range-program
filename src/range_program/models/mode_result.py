from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeResult:
    """Метрики одного режима (conservative / balanced / aggressive) после сравнения на истории."""

    mode: str
    lifetime_days: float
    hit_upper: bool
    hit_lower: bool
    max_deviation_pct: float
    stale_days: float
    ok_days: float
    warning_days: float
    score: float
    summary: str
