from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, NamedTuple

import ccxt

from range_program.config import (
    CCXT_RETRY_BACKOFF_SEC,
    CCXT_RETRY_COUNT,
    CCXT_TIMEOUT_MS,
    DEFAULT_EXCHANGE_ID,
    DEFAULT_QUOTE_ASSET,
    FALLBACK_EXCHANGES,
    FALLBACK_QUOTE_ASSETS,
)
from range_program.models.candle import Candle
from range_program.models.coin import Coin
from range_program.models.market_symbol_match import MarketSymbolMatch


class MarketDataError(Exception):
    """Ошибка получения данных с биржи (сообщение можно показать пользователю)."""


class PriceQuote(NamedTuple):
    price: float
    as_of: datetime


def _base_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if "/" in s:
        return s.split("/")[0].strip()
    return Coin.normalize_symbol(s)


def _ms_to_utc(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)


def _exchange_order(preferred: str | None) -> list[str]:
    """Предпочтительная биржа первая, затем FALLBACK_EXCHANGES без дубликатов."""
    seen: set[str] = set()
    out: list[str] = []
    if preferred:
        p = preferred.strip().lower()
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    for ex in FALLBACK_EXCHANGES:
        if ex not in seen:
            out.append(ex)
            seen.add(ex)
    return out


def _quote_order(preferred: str | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if preferred:
        p = preferred.strip().upper()
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    for q in FALLBACK_QUOTE_ASSETS:
        if q not in seen:
            out.append(q)
            seen.add(q)
    return out


def _quote_from_pair(symbol_pair: str) -> str:
    if "/" in symbol_pair:
        return symbol_pair.split("/", 1)[1].strip().upper()
    return DEFAULT_QUOTE_ASSET


class MarketDataService:
    """Загрузка котировок и свечей через ccxt; fallback по биржам и котируемым активам."""

    def __init__(
        self,
        *,
        exchange_id: str = DEFAULT_EXCHANGE_ID,
        quote_asset: str = DEFAULT_QUOTE_ASSET,
    ) -> None:
        self._default_exchange_id = exchange_id.strip().lower()
        self._default_quote = quote_asset.strip().upper()
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._log = logging.getLogger("range_program.market_data")

    def _get_exchange(self, exchange_id: str) -> ccxt.Exchange:
        eid = exchange_id.strip().lower()
        if eid not in self._exchanges:
            if not hasattr(ccxt, eid):
                raise MarketDataError(f"Неизвестная биржа в ccxt: {eid}")
            ex_class = getattr(ccxt, eid)
            self._exchanges[eid] = ex_class(
                {
                    "enableRateLimit": True,
                    "timeout": CCXT_TIMEOUT_MS,
                }
            )
        return self._exchanges[eid]

    def pair_for_symbol(self, symbol: str, coin: Coin | None = None) -> str:
        """Строка пары для отображения; при сохранённом resolved — как в хранилище."""
        if coin is not None and coin.resolved_symbol_pair:
            return coin.resolved_symbol_pair
        base = _base_symbol(symbol)
        q = self._default_quote
        if coin is not None and coin.quote_asset:
            q = coin.quote_asset.strip().upper()
        return f"{base}/{q}"

    def _map_ccxt_error(self, pair: str, exc: BaseException) -> MarketDataError:
        if isinstance(exc, ccxt.BadSymbol):
            return MarketDataError(f"Нет такой пары на бирже: {pair}.")
        if isinstance(exc, ccxt.NetworkError):
            return MarketDataError(f"Ошибка сети при обращении к бирже: {exc}")
        if isinstance(exc, ccxt.ExchangeError):
            return MarketDataError(f"Ответ биржи: {exc}")
        if isinstance(exc, ccxt.BaseError):
            return MarketDataError(f"Ошибка биржи: {exc}")
        return MarketDataError(f"Не удалось получить данные: {exc}")

    def _is_retryable_ccxt_error(self, exc: BaseException) -> bool:
        return isinstance(
            exc,
            (
                ccxt.NetworkError,
                ccxt.RequestTimeout,
                ccxt.ExchangeNotAvailable,
                ccxt.DDoSProtection,
                ccxt.RateLimitExceeded,
            ),
        )

    def _call_ccxt_with_retries(self, label: str, fn) -> Any:
        retries = int(CCXT_RETRY_COUNT)
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as e:
                if attempt >= retries or not self._is_retryable_ccxt_error(e):
                    raise
                delay = float(CCXT_RETRY_BACKOFF_SEC) * float(attempt + 1)
                self._log.warning(
                    "%s failed (%s/%s), retrying in %.1fs: %s",
                    label,
                    attempt + 1,
                    retries + 1,
                    delay,
                    e,
                )
                time.sleep(delay)

    def _try_fetch_ticker(self, exchange_id: str, pair: str) -> dict[str, Any] | None:
        ex = self._get_exchange(exchange_id)
        try:
            return ex.fetch_ticker(pair)
        except Exception:
            return None

    def resolve_market(self, coin: Coin) -> MarketSymbolMatch:
        """
        Находит первую рабочую пару (fetch_ticker) по preferred/cache и fallback.
        """
        base = coin.symbol.strip().upper()
        tried_labels: list[str] = []

        # 1) Кэш: сначала пробуем последний успешный рынок
        if coin.resolved_exchange and coin.resolved_symbol_pair:
            rex = coin.resolved_exchange.strip().lower()
            pair = coin.resolved_symbol_pair.strip().upper()
            tried_labels.append(f"{rex}:{pair}")
            t = self._try_fetch_ticker(rex, pair)
            if t is not None:
                return MarketSymbolMatch(
                    exchange=rex,
                    symbol_pair=pair,
                    quote_asset=_quote_from_pair(pair),
                )

        ex_list = _exchange_order(coin.exchange)
        q_list = _quote_order(coin.quote_asset)

        # Сначала котируемый актив (USDT → USDC → USD), внутри — биржи по fallback.
        for quote in q_list:
            for ex_id in ex_list:
                pair = f"{base}/{quote}"
                label = f"{ex_id}:{pair}"
                if label in tried_labels:
                    continue
                tried_labels.append(label)
                t = self._try_fetch_ticker(ex_id, pair)
                if t is not None:
                    return MarketSymbolMatch(exchange=ex_id, symbol_pair=pair, quote_asset=quote)

        ex_s = ", ".join(FALLBACK_EXCHANGES)
        q_s = ", ".join(FALLBACK_QUOTE_ASSETS)
        raise MarketDataError(
            f"market not found for symbol {base}: tried exchanges: {ex_s}; tried quotes: {q_s}"
        )

    def fetch_price_quote_with_match(self, match: MarketSymbolMatch) -> PriceQuote:
        ex = self._get_exchange(match.exchange)
        try:
            ticker: dict[str, Any] = self._call_ccxt_with_retries(
                f"fetch_ticker {match.exchange}:{match.symbol_pair}",
                lambda: ex.fetch_ticker(match.symbol_pair),
            )
        except Exception as e:
            err = self._map_ccxt_error(match.symbol_pair, e)
            self._log.warning("%s", err)
            raise err from e

        last = ticker.get("last")
        if last is None:
            close = ticker.get("close")
            if close is not None:
                last = close
        if last is None:
            raise MarketDataError("Биржа не вернула цену (last/close пусто).")

        price = float(last)
        ts = ticker.get("timestamp")
        as_of = _ms_to_utc(ts) if ts is not None else datetime.now(timezone.utc)
        return PriceQuote(price=price, as_of=as_of)

    def fetch_ohlcv_with_match(
        self, match: MarketSymbolMatch, timeframe: str, limit: int
    ) -> list[Candle]:
        ex = self._get_exchange(match.exchange)
        if limit < 1:
            raise MarketDataError("limit должен быть не меньше 1.")
        try:
            raw = self._call_ccxt_with_retries(
                f"fetch_ohlcv {match.exchange}:{match.symbol_pair} tf={timeframe} limit={limit}",
                lambda: ex.fetch_ohlcv(match.symbol_pair, timeframe=timeframe, limit=limit),
            )
        except Exception as e:
            err = self._map_ccxt_error(match.symbol_pair, e)
            self._log.warning("%s", err)
            raise err from e
        return self._parse_ohlcv_raw(raw)

    def get_price_quote(self, symbol: str, *, coin: Coin | None = None) -> PriceQuote:
        """Текущая цена; без Coin — только default биржа и QUOTE (обратная совместимость)."""
        if coin is None:
            pair = f"{_base_symbol(symbol)}/{self._default_quote}"
            ex = self._get_exchange(self._default_exchange_id)
            try:
                ticker: dict[str, Any] = self._call_ccxt_with_retries(
                    f"fetch_ticker {self._default_exchange_id}:{pair}",
                    lambda: ex.fetch_ticker(pair),
                )
            except Exception as e:
                err = self._map_ccxt_error(pair, e)
                self._log.warning("%s", err)
                raise err from e
            last = ticker.get("last")
            if last is None and ticker.get("close") is not None:
                last = ticker.get("close")
            if last is None:
                raise MarketDataError("Биржа не вернула цену (last/close пусто).")
            ts = ticker.get("timestamp")
            as_of = _ms_to_utc(ts) if ts is not None else datetime.now(timezone.utc)
            return PriceQuote(price=float(last), as_of=as_of)

        match = self.resolve_market(coin)
        return self.fetch_price_quote_with_match(match)

    def get_current_price(self, symbol: str, *, coin: Coin | None = None) -> float:
        return self.get_price_quote(symbol, coin=coin).price

    def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int, *, coin: Coin | None = None
    ) -> list[Candle]:
        if coin is None:
            pair = f"{_base_symbol(symbol)}/{self._default_quote}"
            ex = self._get_exchange(self._default_exchange_id)
            if limit < 1:
                raise MarketDataError("limit должен быть не меньше 1.")
            try:
                raw = self._call_ccxt_with_retries(
                    f"fetch_ohlcv {self._default_exchange_id}:{pair} tf={timeframe} limit={limit}",
                    lambda: ex.fetch_ohlcv(pair, timeframe=timeframe, limit=limit),
                )
            except Exception as e:
                err = self._map_ccxt_error(pair, e)
                self._log.warning("%s", err)
                raise err from e
            return self._parse_ohlcv_raw(raw)

        match = self.resolve_market(coin)
        return self.fetch_ohlcv_with_match(match, timeframe, limit)

    def _parse_ohlcv_raw(self, raw: Any) -> list[Candle]:
        if raw is None:
            raise MarketDataError("Биржа вернула пустой ответ по свечам.")
        if len(raw) == 0:
            raise MarketDataError("Нет свечей для этой пары и таймфрейма (пустой список).")
        out: list[Candle] = []
        for row in raw:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            ts_ms, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            ts = _ms_to_utc(ts_ms)
            if ts is None:
                continue
            out.append(
                Candle(
                    timestamp=ts,
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                )
            )
        if not out:
            raise MarketDataError("Не удалось разобрать свечи (неожиданный формат ответа).")
        return out
