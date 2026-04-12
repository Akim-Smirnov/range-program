from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSymbolMatch:
    """Найденный на бирже рынок для базового тикера."""

    exchange: str
    symbol_pair: str
    quote_asset: str
