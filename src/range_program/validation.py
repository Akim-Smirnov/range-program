from __future__ import annotations

from range_program.models.defaults import ALLOWED_CENTER_METHODS, ALLOWED_MODES, ALLOWED_WIDTH_METHODS


class ValidationError(Exception):
    """Ошибка проверки входных данных (доменная)."""


def validate_mode(mode: str) -> None:
    if mode not in ALLOWED_MODES:
        allowed = ", ".join(sorted(ALLOWED_MODES))
        raise ValidationError(f"mode must be one of: {allowed}")


def validate_center_method(center_method: str) -> None:
    cm = center_method.strip().lower()
    if cm not in ALLOWED_CENTER_METHODS:
        allowed = ", ".join(sorted(ALLOWED_CENTER_METHODS))
        raise ValidationError(f"center_method must be one of: {allowed}")


def validate_width_method(width_method: str) -> None:
    wm = width_method.strip().lower()
    if wm not in ALLOWED_WIDTH_METHODS:
        allowed = ", ".join(sorted(ALLOWED_WIDTH_METHODS))
        raise ValidationError(f"width_method must be one of: {allowed}")


def validate_range_bounds(low: float, high: float) -> None:
    if low >= high:
        raise ValidationError("low must be strictly less than high")


def validate_capital(capital: float | None) -> None:
    """Капитал по монете: либо не задан, либо строго положительный."""
    if capital is None:
        return
    if capital <= 0:
        raise ValidationError("capital must be positive")
