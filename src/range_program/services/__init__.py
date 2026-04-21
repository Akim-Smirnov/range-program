"""
Пакет сервисов (бизнес-логика).

Содержит основные сервисы приложения (монеты, рынок, пересчёт диапазона, check и т.д.).
`__init__` реэкспортирует основные классы и исключения для удобного импорта.
"""

from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataError, MarketDataService, PriceQuote
from range_program.services.range_engine import RangeEngine, RangeEngineError
from range_program.services.recalc_service import RecalcOutcome, RecalcService
from range_program.services.check_service import CheckService
from range_program.services.evaluator import Evaluator, EvaluatorError

__all__ = [
    "CoinService",
    "MarketDataError",
    "MarketDataService",
    "PriceQuote",
    "RangeEngine",
    "RangeEngineError",
    "RecalcOutcome",
    "RecalcService",
    "CheckService",
    "Evaluator",
    "EvaluatorError",
]
