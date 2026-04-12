"""Настройки источника рыночных данных (этап 4)."""

# Идентификатор биржи в ccxt (по умолчанию Binance spot).
DEFAULT_EXCHANGE_ID = "binance"

# Котируемый актив для пары BASE/QUOTE (например BTC/USDT).
DEFAULT_QUOTE_ASSET = "USDT"

# Порядок бирж и котируемых активов для автопоиска рынка (fallback).
FALLBACK_EXCHANGES: tuple[str, ...] = ("binance", "bybit", "okx", "kucoin")
FALLBACK_QUOTE_ASSETS: tuple[str, ...] = ("USDT", "USDC", "USD")
