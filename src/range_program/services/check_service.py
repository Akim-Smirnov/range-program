from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from range_program.models.check_result import CheckResult
from range_program.models.coin import Coin
from range_program.models.market_symbol_match import MarketSymbolMatch
from range_program.services.coin_service import CoinService
from range_program.services.evaluator import Evaluator, EvaluatorError
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.recommended_range_freshness import is_recommended_range_stale
from range_program.services.range_engine import RangeEngineError
from range_program.services.recalc_service import RecalcService
from range_program.validation import ValidationError

from range_program.check_all_report import CheckTableRow
from range_program.repositories.check_history_repository import CheckHistoryRepository

_log = logging.getLogger("range_program.check_service")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _quote_from_pair(symbol_pair: str) -> str:
    if "/" in symbol_pair:
        return symbol_pair.split("/", 1)[1].strip().upper()
    return "USDT"


class CheckService:
    """Оркестрация check: рынок, при необходимости recalc, Evaluator, сохранение last_check."""

    def __init__(
        self,
        coins: CoinService,
        market: MarketDataService,
        recalc: RecalcService,
        evaluator: Evaluator | None = None,
        history: CheckHistoryRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._coins = coins
        self._market = market
        self._recalc = recalc
        self._eval = evaluator or Evaluator()
        self._history = history
        self._now = now_provider or _utc_now

    def run_check(self, symbol: str, *, auto_recalc: bool = True) -> CheckResult:
        sym = Coin.normalize_symbol(symbol)
        coin = self._coins.get_coin(sym)
        if coin is None:
            raise ValidationError(f"Монета {sym} не найдена в хранилище.")

        if coin.active_range is None:
            raise ValidationError(
                f"У монеты {sym} нет активного диапазона. Задайте в меню: Coins → «Задать active range»."
            )

        recalc_reason: str | None = self._recalc_reason(coin)
        if recalc_reason is not None:
            if auto_recalc:
                try:
                    self._recalc.recalc(sym)
                except (ValidationError, MarketDataError, RangeEngineError) as e:
                    raise ValidationError(
                        f"{recalc_reason}; автоматический recalc не удался: {e}"
                    ) from e
                _log.info("auto recalc before check symbol=%s reason=%s", sym, recalc_reason)
                coin = self._coins.get_coin(sym)
                if coin is None or coin.recommended_range is None:
                    raise ValidationError(
                        "После recalc рекомендуемый диапазон по-прежнему отсутствует. Проверьте настройки и сеть."
                    )
            else:
                # Если recalc отключён, то при отсутствии recommended_range проверка бессмысленна.
                if coin.recommended_range is None:
                    raise ValidationError(
                        f"{recalc_reason}. Автоматический recalc отключён — выполните recalc вручную в Range analysis."
                    )
                _log.info("skip auto recalc symbol=%s reason=%s", sym, recalc_reason)

        match: MarketSymbolMatch | None = None
        try:
            # Быстрый путь: если рынок уже был определён, не делаем resolve_market (экономим запрос ticker).
            if coin.resolved_exchange and coin.resolved_symbol_pair:
                cached = MarketSymbolMatch(
                    exchange=coin.resolved_exchange,
                    symbol_pair=coin.resolved_symbol_pair,
                    quote_asset=_quote_from_pair(coin.resolved_symbol_pair),
                )
                try:
                    price = self._market.fetch_price_quote_with_match(cached).price
                    match = cached
                except MarketDataError as e:
                    _log.warning("cached price fetch failed symbol=%s: %s", sym, e)

            if match is None:
                match = self._market.resolve_market(coin)
                price = self._market.fetch_price_quote_with_match(match).price
        except MarketDataError as e:
            _log.warning("price fetch failed symbol=%s: %s", sym, e)
            raise ValidationError(f"Не удалось получить текущую цену: {e}. Проверьте интернет/доступность биржи.") from e

        try:
            result = self._eval.evaluate(coin, price)
        except EvaluatorError as e:
            _log.warning("evaluator failed symbol=%s: %s", sym, e)
            raise ValidationError(str(e)) from e

        now = self._now()
        updated = replace(
            coin,
            last_check=result,
            updated_at=now,
            resolved_exchange=match.exchange if match is not None else coin.resolved_exchange,
            resolved_symbol_pair=match.symbol_pair if match is not None else coin.resolved_symbol_pair,
            resolved_at=now if match is not None else coin.resolved_at,
        )
        if not self._coins.update_coin(updated):
            raise ValidationError(f"Не удалось сохранить результат проверки для {sym}.")

        if self._history is not None:
            self._history.save_check(result)

        return result

    def _recalc_reason(self, coin: Coin) -> str | None:
        if coin.recommended_range is None:
            return "Нет рекомендуемого диапазона"
        if is_recommended_range_stale(
            calculated_at=coin.recommended_range.calculated_at,
            timeframe=coin.timeframe,
            now_utc=self._now(),
        ):
            return "Рекомендуемый диапазон устарел"
        return None

    def run_check_safe(self, symbol: str, *, auto_recalc: bool = True) -> tuple[CheckResult | None, str | None]:
        """То же, что run_check, но без исключений — для массовой проверки."""
        try:
            return self.run_check(symbol, auto_recalc=auto_recalc), None
        except ValidationError as e:
            return None, str(e)

    def run_check_all(self, *, auto_recalc: bool = True) -> list[CheckTableRow]:
        """Проверить все монеты из хранилища; ошибки по одной монете не прерывают остальные."""
        rows: list[CheckTableRow] = []
        for coin in self._coins.list_coins():
            res, err = self.run_check_safe(coin.symbol, auto_recalc=auto_recalc)
            if res is not None:
                rows.append(CheckTableRow.from_check_result(res))
            else:
                rows.append(CheckTableRow.error_row(coin.symbol, err or "unknown error"))
        rows.sort(key=lambda r: (r.sort_rank, r.symbol))
        return rows
