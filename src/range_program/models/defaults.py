"""Значения по умолчанию для новой монеты (этап 3)."""

DEFAULT_MODE = "balanced"
DEFAULT_TIMEFRAME = "4h"
DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_CENTER_METHOD = "ema"
DEFAULT_WIDTH_METHOD = "atr"

ALLOWED_MODES = frozenset({"conservative", "balanced", "aggressive"})
