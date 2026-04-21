"""
Результат сопоставления монеты с рынком на бирже.

Файл описывает найденную торговую пару на выбранной бирже и котируемый актив, чтобы
дальше получать цену и кэшировать успешное сопоставление.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSymbolMatch:
    """Найденный на бирже рынок: `exchange`, `symbol_pair` и `quote_asset`."""

    exchange: str
    symbol_pair: str
    quote_asset: str
