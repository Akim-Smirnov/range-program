"""
Модель монеты (Coin) и её настройки для Range Program.

`Coin` это центральная доменная сущность проекта. В ней хранятся:
- настройки расчёта диапазона (mode/timeframe/lookback_days/center_method/width_method),
- рыночный контекст (exchange/quote_asset и кэш последнего успешного сопоставления рынка),
- диапазоны (active_range и calculated recommended_range),
- последняя проверка (last_check) и служебные времена.

Модель неизменяемая (`frozen=True`), изменения выполняются через `dataclasses.replace(...)`,
`with_settings(...)` или `create(...)` при создании новой монеты.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class Coin:
    """
    Монета и все связанные с ней настройки и состояние.

    Экземпляр нормализует строковые поля (symbol/mode/timeframe/center_method/width_method)
    в `__post_init__`, чтобы данные в `data/` были единообразными.
    """

    # Базовые настройки пользователя
    symbol: str
    created_at: datetime
    mode: str
    timeframe: str
    lookback_days: int
    center_method: str
    width_method: str
    updated_at: datetime

    # Дополнительные настройки/контекст рынка
    capital: float | None = None
    exchange: str | None = None
    quote_asset: str | None = None

    # Кэш “последнего успешно найденного рынка” (ускоряет resolve_market)
    resolved_exchange: str | None = None
    resolved_symbol_pair: str | None = None
    resolved_at: datetime | None = None

    # Диапазоны и история
    active_range: ActiveRange | None = None
    recommended_range: RecommendedRange | None = None
    last_check: CheckResult | None = None

    def __post_init__(self) -> None:
        # Делаем нормализацию строковых полей единообразно в одном месте,
        # чтобы в data/ не накапливались разные регистры/пробелы.
        object.__setattr__(self, "symbol", self.normalize_symbol(self.symbol))
        object.__setattr__(self, "mode", self.normalize_mode(self.mode))
        object.__setattr__(self, "timeframe", self.normalize_timeframe(self.timeframe))
        object.__setattr__(self, "center_method", self.normalize_center_method(self.center_method))
        object.__setattr__(self, "width_method", self.normalize_width_method(self.width_method))

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def normalize_mode(mode: str) -> str:
        return mode.strip().lower()

    @staticmethod
    def normalize_timeframe(timeframe: str) -> str:
        return timeframe.strip().lower()

    @staticmethod
    def normalize_center_method(center_method: str) -> str:
        return center_method.strip().lower()

    @staticmethod
    def normalize_width_method(width_method: str) -> str:
        return width_method.strip().lower()

    def normalized(self) -> Coin:
        """Вернуть копию монеты с нормализованными строковыми полями."""
        return replace(
            self,
            symbol=self.normalize_symbol(self.symbol),
            mode=self.normalize_mode(self.mode),
            timeframe=self.normalize_timeframe(self.timeframe),
            center_method=self.normalize_center_method(self.center_method),
            width_method=self.normalize_width_method(self.width_method),
        )

    def with_settings(
        self,
        *,
        mode: str | None = None,
        timeframe: str | None = None,
        lookback_days: int | None = None,
        center_method: str | None = None,
        width_method: str | None = None,
    ) -> Coin:
        """
        Вернуть копию монеты с обновлёнными настройками расчёта.

        Удобно для "примерки" настроек (override) и единообразной нормализации входных строк.
        """
        updated = self
        if mode is not None:
            updated = replace(updated, mode=self.normalize_mode(mode))
        if timeframe is not None:
            updated = replace(updated, timeframe=self.normalize_timeframe(timeframe))
        if lookback_days is not None:
            updated = replace(updated, lookback_days=int(lookback_days))
        if center_method is not None:
            updated = replace(updated, center_method=self.normalize_center_method(center_method))
        if width_method is not None:
            updated = replace(updated, width_method=self.normalize_width_method(width_method))
        return updated

    @classmethod
    def create(
        cls,
        symbol: str,
        *,
        created_at: datetime | None = None,
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
        ca = created_at or now
        return cls(
            symbol=sym,
            created_at=ca,
            mode=cls.normalize_mode(mode),
            timeframe=cls.normalize_timeframe(timeframe),
            lookback_days=lookback_days,
            center_method=cls.normalize_center_method(center_method),
            width_method=cls.normalize_width_method(width_method),
            updated_at=ca,
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
