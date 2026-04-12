from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from range_program.models.active_range import ActiveRange
from range_program.models.check_result import CheckResult
from range_program.models.recommended_range import RecommendedRange
from range_program.models.defaults import (
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Coin:
    symbol: str
    created_at: datetime
    mode: str
    timeframe: str
    lookback_days: int
    center_method: str
    width_method: str
    updated_at: datetime
    capital: float | None = None
    exchange: str | None = None
    quote_asset: str | None = None
    resolved_exchange: str | None = None
    resolved_symbol_pair: str | None = None
    resolved_at: datetime | None = None
    active_range: ActiveRange | None = None
    recommended_range: RecommendedRange | None = None
    last_check: CheckResult | None = None

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @classmethod
    def create(
        cls,
        symbol: str,
        *,
        mode: str = DEFAULT_MODE,
        timeframe: str = DEFAULT_TIMEFRAME,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        center_method: str = DEFAULT_CENTER_METHOD,
        width_method: str = DEFAULT_WIDTH_METHOD,
        capital: float | None = None,
        exchange: str | None = None,
        quote_asset: str | None = None,
        resolved_exchange: str | None = None,
        resolved_symbol_pair: str | None = None,
        resolved_at: datetime | None = None,
        active_range: ActiveRange | None = None,
        recommended_range: RecommendedRange | None = None,
        last_check: CheckResult | None = None,
    ) -> Coin:
        sym = cls.normalize_symbol(symbol)
        now = _utc_now()
        return cls(
            symbol=sym,
            created_at=now,
            mode=mode,
            timeframe=timeframe,
            lookback_days=lookback_days,
            center_method=center_method,
            width_method=width_method,
            updated_at=now,
            capital=capital,
            exchange=exchange,
            quote_asset=quote_asset,
            resolved_exchange=resolved_exchange,
            resolved_symbol_pair=resolved_symbol_pair,
            resolved_at=resolved_at,
            active_range=active_range,
            recommended_range=recommended_range,
            last_check=last_check,
        )
