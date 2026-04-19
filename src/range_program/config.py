"""
Конфигурация Range Program.

Файл хранит “разумные дефолты” для разных частей программы:
- настройки источников рыночных данных (ccxt),
- параметры/пороги для оценок (Evaluator) и вывода.

Если нужно “настроить поведение”, это обычно делается через значения здесь,
а не через правки бизнес-логики.
"""

# Идентификатор биржи в ccxt (по умолчанию Binance spot).
DEFAULT_EXCHANGE_ID = "binance"

# Котируемый актив для пары BASE/QUOTE (например BTC/USDT).
DEFAULT_QUOTE_ASSET = "USDT"

# Порядок бирж и котируемых активов для автопоиска рынка (fallback).
FALLBACK_EXCHANGES: tuple[str, ...] = ("binance", "bybit", "okx", "kucoin")
FALLBACK_QUOTE_ASSETS: tuple[str, ...] = ("USDT", "USDC", "USD")

# --- Evaluator (регулярный контроль) ---
# Порог “близко к краю” как доля ширины active_range (0.05 = 5%).
EVAL_NEAR_EDGE_FRAC = 0.05

# STALE: отклонение цены от центра active_range (в %) выше этого порога.
EVAL_STALE_DEVIATION_PCT = 12.0

# REPOSITION: расхождение центров (recommended vs active) (в %) выше этого порога.
EVAL_REPOSITION_CENTER_DIFF_PCT = 10.0
