"""
Пакет доменных моделей.

Содержит dataclass-модели (Coin, диапазоны, результаты check/backtest и т.д.).
`__init__` реэкспортирует основные сущности для импорта из `range_program.models`.
"""

from range_program.models.active_range import ActiveRange
from range_program.models.backtest_result import BacktestResult
from range_program.models.candle import Candle
from range_program.models.check_result import CheckResult
from range_program.models.coin import Coin
from range_program.models.grid_config import GridConfig
from range_program.models.market_symbol_match import MarketSymbolMatch
from range_program.models.mode_result import ModeResult
from range_program.models.recommended_range import RecommendedRange
from range_program.models.defaults import (
    ALLOWED_CENTER_METHODS,
    ALLOWED_MODES,
    ALLOWED_WIDTH_METHODS,
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)

__all__ = [
    "ActiveRange",
    "BacktestResult",
    "Candle",
    "CheckResult",
    "ALLOWED_CENTER_METHODS",
    "ALLOWED_MODES",
    "ALLOWED_WIDTH_METHODS",
    "Coin",
    "GridConfig",
    "MarketSymbolMatch",
    "ModeResult",
    "RecommendedRange",
    "DEFAULT_CENTER_METHOD",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_MODE",
    "DEFAULT_TIMEFRAME",
    "DEFAULT_WIDTH_METHOD",
]
