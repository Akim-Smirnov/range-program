from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from range_program.models.active_range import ActiveRange
from range_program.models.coin import Coin
from range_program.models.defaults import (
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)
from range_program.repositories.coin_repository import CoinRepository
from range_program.validation import (
    ValidationError,
    validate_capital,
    validate_center_method,
    validate_lookback_days,
    validate_mode,
    validate_range_bounds,
    validate_timeframe,
    validate_width_method,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_log = logging.getLogger("range_program.coin_service")


class CoinService:
    """
    Сервис управления монетами (слой над репозиторием).

    Отвечает за:
    - добавление/удаление монеты в локальное хранилище,
    - изменение пользовательских настроек (capital, active_range и т.п.),
    - валидацию входных параметров на доменном уровне.

    Важно: сервис работает с неизменяемыми моделями (Coin) и обновляет их
    через `dataclasses.replace(...)`.
    """

    def __init__(self, repository: CoinRepository | None = None) -> None:
        self._repo = repository or CoinRepository()

    @property
    def data_path(self) -> Path:
        return self._repo.path

    def add_coin(
        self,
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
    ) -> tuple[bool, Coin | None]:
        """Добавляет монету в список и возвращает (ok, coin)."""
        validate_mode(mode)
        validate_timeframe(timeframe)
        validate_lookback_days(lookback_days)
        validate_center_method(center_method)
        validate_width_method(width_method)
        validate_capital(capital)
        norm = Coin.normalize_symbol(symbol)
        ok = self._repo.add_coin(
            symbol,
            mode=mode,
            timeframe=timeframe,
            lookback_days=lookback_days,
            center_method=center_method,
            width_method=width_method,
            capital=capital,
            exchange=exchange,
            quote_asset=quote_asset,
        )
        return ok, self._repo.get_coin(norm)

    def set_capital(self, symbol: str, capital: float) -> Coin:
        """Задаёт капитал для расчёта вариантов сетки (grid_configs) при recalc."""
        validate_capital(capital)
        norm = Coin.normalize_symbol(symbol)
        coin = self._repo.get_coin(norm)
        if coin is None:
            raise ValidationError(f"Монета {norm} не найдена.")
        updated = replace(coin, capital=float(capital), updated_at=_utc_now())
        self._repo.update_coin(updated)
        return updated

    def clear_capital(self, symbol: str) -> Coin:
        """Сбрасывает капитал (после этого варианты сетки не рассчитываются)."""
        norm = Coin.normalize_symbol(symbol)
        coin = self._repo.get_coin(norm)
        if coin is None:
            raise ValidationError(f"Монета {norm} не найдена.")
        updated = replace(coin, capital=None, updated_at=_utc_now())
        self._repo.update_coin(updated)
        return updated

    def remove_coin(self, symbol: str) -> bool:
        return self._repo.remove_coin(symbol)

    def list_coins(self) -> list[Coin]:
        return self._repo.list_coins()

    def get_coin(self, symbol: str) -> Coin | None:
        return self._repo.get_coin(symbol)

    def update_coin(self, coin: Coin) -> bool:
        return self._repo.update_coin(coin)

    def set_active_range(
        self,
        symbol: str,
        low: float,
        high: float,
        *,
        comment: str | None = None,
    ) -> Coin:
        """Сохраняет активный диапазон (как стоит бот) для монеты."""
        validate_range_bounds(low, high)
        norm = Coin.normalize_symbol(symbol)
        coin = self._repo.get_coin(norm)
        if coin is None:
            raise ValidationError(f"Монета {norm} не найдена.")
        now = _utc_now()
        ar = ActiveRange(low=low, high=high, set_at=now, comment=comment)
        updated = replace(coin, active_range=ar, updated_at=now)
        self._repo.update_coin(updated)
        _log.info("set_active_range symbol=%s low=%s high=%s comment=%r", norm, low, high, comment)
        return updated

    def clear_active_range(self, symbol: str, *, comment: str | None = None) -> Coin:
        """Сбрасывает активный диапазон. `comment` пишется в лог (active_range очищается полностью)."""
        norm = Coin.normalize_symbol(symbol)
        coin = self._repo.get_coin(norm)
        if coin is None:
            raise ValidationError(f"Монета {norm} не найдена.")
        now = _utc_now()
        updated = replace(coin, active_range=None, updated_at=now)
        self._repo.update_coin(updated)
        _log.info("clear_active_range symbol=%s comment=%r", norm, comment)
        return updated

    def clear_active(self, symbol: str) -> Coin:
        """Алиас для обратной совместимости: сбросить active_range."""
        return self.clear_active_range(symbol)
