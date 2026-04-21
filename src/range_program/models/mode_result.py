"""
Агрегированные метрики одного режима на истории.

Файл содержит модель результата сравнения режимов (conservative/balanced/aggressive):
длительность "жизни" диапазона, касания границ, качество и итоговый score/summary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeResult:
    """Метрики одного режима после сравнения на истории (для отчёта и выбора режима)."""

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
