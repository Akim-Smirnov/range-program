from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from range_program.models.active_range import ActiveRange
from range_program.models.check_result import CheckResult
from range_program.models.coin import Coin
from range_program.models.grid_config import GridConfig
from range_program.models.recommended_range import RecommendedRange
from range_program.models.defaults import (
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)


def _default_data_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "coins.json"


def _parse_dt(value: str) -> datetime:
    raw = value.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def _active_range_to_dict(ar: ActiveRange) -> dict[str, Any]:
    d: dict[str, Any] = {
        "low": ar.low,
        "high": ar.high,
        "set_at": ar.set_at.isoformat(),
    }
    if ar.comment is not None:
        d["comment"] = ar.comment
    return d


def _grid_config_to_dict(gc: GridConfig) -> dict[str, Any]:
    return {
        "mode": gc.mode,
        "grid_count": gc.grid_count,
        "step_pct": gc.step_pct,
        "order_size": gc.order_size,
    }


def _grid_config_from_dict(data: dict[str, Any]) -> GridConfig:
    return GridConfig(
        mode=str(data["mode"]),
        grid_count=int(data["grid_count"]),
        step_pct=float(data["step_pct"]),
        order_size=float(data["order_size"]),
    )


def _recommended_range_to_dict(rr: RecommendedRange) -> dict[str, Any]:
    d: dict[str, Any] = {
        "low": rr.low,
        "high": rr.high,
        "center": rr.center,
        "width_pct": rr.width_pct,
        "calculated_at": rr.calculated_at.isoformat(),
        "center_method": rr.center_method,
        "width_method": rr.width_method,
        "grid_configs": [_grid_config_to_dict(g) for g in rr.grid_configs],
    }
    return d


def _check_result_to_dict(cr: CheckResult) -> dict[str, Any]:
    return {
        "symbol": cr.symbol,
        "current_price": cr.current_price,
        "active_low": cr.active_low,
        "active_high": cr.active_high,
        "active_center": cr.active_center,
        "recommended_low": cr.recommended_low,
        "recommended_high": cr.recommended_high,
        "recommended_center": cr.recommended_center,
        "distance_to_lower_pct": cr.distance_to_lower_pct,
        "distance_to_upper_pct": cr.distance_to_upper_pct,
        "deviation_from_active_center_pct": cr.deviation_from_active_center_pct,
        "status": cr.status,
        "recommendation": cr.recommendation,
        "checked_at": cr.checked_at.isoformat(),
    }


def _check_result_from_dict(data: dict[str, Any]) -> CheckResult:
    return CheckResult(
        symbol=str(data["symbol"]),
        current_price=float(data["current_price"]),
        active_low=float(data["active_low"]),
        active_high=float(data["active_high"]),
        active_center=float(data["active_center"]),
        recommended_low=float(data["recommended_low"]),
        recommended_high=float(data["recommended_high"]),
        recommended_center=float(data["recommended_center"]),
        distance_to_lower_pct=float(data["distance_to_lower_pct"]),
        distance_to_upper_pct=float(data["distance_to_upper_pct"]),
        deviation_from_active_center_pct=float(data["deviation_from_active_center_pct"]),
        status=str(data["status"]),
        recommendation=str(data["recommendation"]),
        checked_at=_parse_dt(str(data["checked_at"])),
    )


def _recommended_range_from_dict(data: dict[str, Any]) -> RecommendedRange:
    raw_gc = data.get("grid_configs")
    grid_configs: tuple[GridConfig, ...] = ()
    if raw_gc is not None:
        if not isinstance(raw_gc, list):
            raise ValueError("recommended_range.grid_configs must be a list or null")
        parsed: list[GridConfig] = []
        for item in raw_gc:
            if not isinstance(item, dict):
                raise ValueError("grid_configs entries must be objects")
            parsed.append(_grid_config_from_dict(item))
        grid_configs = tuple(parsed)

    return RecommendedRange(
        low=float(data["low"]),
        high=float(data["high"]),
        center=float(data["center"]),
        width_pct=float(data["width_pct"]),
        calculated_at=_parse_dt(str(data["calculated_at"])),
        center_method=str(data["center_method"]),
        width_method=str(data["width_method"]),
        grid_configs=grid_configs,
    )


def _active_range_from_dict(data: dict[str, Any]) -> ActiveRange:
    cr = data.get("comment")
    comment: str | None = None if cr is None else str(cr)
    return ActiveRange(
        low=float(data["low"]),
        high=float(data["high"]),
        set_at=_parse_dt(str(data["set_at"])),
        comment=comment,
    )


def _coin_to_dict(coin: Coin) -> dict[str, Any]:
    out: dict[str, Any] = {
        "symbol": coin.symbol,
        "created_at": coin.created_at.isoformat(),
        "mode": coin.mode,
        "timeframe": coin.timeframe,
        "lookback_days": coin.lookback_days,
        "center_method": coin.center_method,
        "width_method": coin.width_method,
        "updated_at": coin.updated_at.isoformat(),
        "capital": coin.capital,
        "exchange": coin.exchange,
        "quote_asset": coin.quote_asset,
        "resolved_exchange": coin.resolved_exchange,
        "resolved_symbol_pair": coin.resolved_symbol_pair,
        "resolved_at": coin.resolved_at.isoformat() if coin.resolved_at is not None else None,
    }
    if coin.active_range is not None:
        out["active_range"] = _active_range_to_dict(coin.active_range)
    else:
        out["active_range"] = None
    if coin.recommended_range is not None:
        out["recommended_range"] = _recommended_range_to_dict(coin.recommended_range)
    else:
        out["recommended_range"] = None
    if coin.last_check is not None:
        out["last_check"] = _check_result_to_dict(coin.last_check)
    else:
        out["last_check"] = None
    return out


def _coin_from_dict(data: dict[str, Any]) -> Coin:
    """Разбор записи монеты; поддерживает старый формат (только symbol + created_at)."""
    if not isinstance(data, dict):
        raise ValueError("coin entry must be a JSON object")

    raw_symbol = data.get("symbol")
    if not isinstance(raw_symbol, str) or not raw_symbol.strip():
        raise ValueError("coin missing valid symbol")

    symbol = Coin.normalize_symbol(raw_symbol)

    if "created_at" not in data:
        raise ValueError(f"coin {symbol}: missing created_at")
    created_at = _parse_dt(str(data["created_at"]))

    mode = str(data.get("mode", DEFAULT_MODE))
    timeframe = str(data.get("timeframe", DEFAULT_TIMEFRAME))
    lookback_days = int(data.get("lookback_days", DEFAULT_LOOKBACK_DAYS))
    center_method = str(data.get("center_method", DEFAULT_CENTER_METHOD))
    width_method = str(data.get("width_method", DEFAULT_WIDTH_METHOD))

    if "updated_at" in data:
        updated_at = _parse_dt(str(data["updated_at"]))
    else:
        updated_at = created_at

    active_range: ActiveRange | None = None
    ar_raw = data.get("active_range")
    if ar_raw is not None:
        if not isinstance(ar_raw, dict):
            raise ValueError(f"coin {symbol}: active_range must be an object or null")
        active_range = _active_range_from_dict(ar_raw)

    recommended_range: RecommendedRange | None = None
    rr_raw = data.get("recommended_range")
    if rr_raw is not None:
        if not isinstance(rr_raw, dict):
            raise ValueError(f"coin {symbol}: recommended_range must be an object or null")
        recommended_range = _recommended_range_from_dict(rr_raw)

    last_check: CheckResult | None = None
    lc_raw = data.get("last_check")
    if lc_raw is not None:
        if not isinstance(lc_raw, dict):
            raise ValueError(f"coin {symbol}: last_check must be an object or null")
        last_check = _check_result_from_dict(lc_raw)

    capital: float | None = None
    if "capital" in data and data["capital"] is not None:
        capital = float(data["capital"])

    exchange: str | None = data.get("exchange")
    if exchange is not None:
        exchange = str(exchange).strip().lower() or None
    quote_asset: str | None = data.get("quote_asset")
    if quote_asset is not None:
        quote_asset = str(quote_asset).strip().upper() or None

    resolved_exchange: str | None = data.get("resolved_exchange")
    if resolved_exchange is not None:
        resolved_exchange = str(resolved_exchange).strip().lower() or None
    resolved_symbol_pair: str | None = data.get("resolved_symbol_pair")
    if resolved_symbol_pair is not None:
        resolved_symbol_pair = str(resolved_symbol_pair).strip().upper() or None
    resolved_at: datetime | None = None
    if data.get("resolved_at") is not None:
        resolved_at = _parse_dt(str(data["resolved_at"]))

    return Coin(
        symbol=symbol,
        created_at=created_at,
        mode=mode,
        timeframe=timeframe,
        lookback_days=lookback_days,
        center_method=center_method,
        width_method=width_method,
        updated_at=updated_at,
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


class CoinRepository:
    """Хранение монет в JSON-файле; вся работа с файлом изолирована здесь."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_data_path()

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def _load_raw_list(self) -> list[dict[str, Any]]:
        self._ensure_file()
        text = self._path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"coins.json is not valid JSON: {e}") from e
        if not isinstance(data, list):
            raise ValueError("coins.json must contain a JSON array")
        return [x for x in data if isinstance(x, dict)]

    def _load_coins(self) -> list[Coin]:
        raw = self._load_raw_list()
        coins: list[Coin] = []
        for i, item in enumerate(raw):
            try:
                coins.append(_coin_from_dict(item))
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"coins.json: invalid coin at index {i}: {e}") from e
        return coins

    def _save_coins(self, coins: list[Coin]) -> None:
        self._ensure_file()
        payload = [_coin_to_dict(c) for c in sorted(coins, key=lambda x: x.symbol)]
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_coins(self) -> list[Coin]:
        return self._load_coins()

    def get_coin(self, symbol: str) -> Coin | None:
        sym = Coin.normalize_symbol(symbol)
        for c in self.list_coins():
            if c.symbol == sym:
                return c
        return None

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
    ) -> bool:
        """Добавить монету с параметрами по умолчанию или заданными. False — дубликат."""
        sym = Coin.normalize_symbol(symbol)
        coins = self._load_coins()
        if any(c.symbol == sym for c in coins):
            return False
        ex = exchange.strip().lower() if exchange else None
        qa = quote_asset.strip().upper() if quote_asset else None
        coins.append(
            Coin.create(
                sym,
                mode=mode,
                timeframe=timeframe,
                lookback_days=lookback_days,
                center_method=center_method,
                width_method=width_method,
                capital=capital,
                exchange=ex or None,
                quote_asset=qa or None,
            )
        )
        self._save_coins(coins)
        return True

    def remove_coin(self, symbol: str) -> bool:
        sym = Coin.normalize_symbol(symbol)
        coins = self._load_coins()
        new_coins = [c for c in coins if c.symbol != sym]
        if len(new_coins) == len(coins):
            return False
        self._save_coins(new_coins)
        return True

    def update_coin(self, coin: Coin) -> bool:
        """Заменить монету с тем же symbol. False — монеты нет в хранилище."""
        sym = coin.symbol
        coins = self._load_coins()
        found = False
        new_list: list[Coin] = []
        for c in coins:
            if c.symbol == sym:
                new_list.append(coin)
                found = True
            else:
                new_list.append(c)
        if not found:
            return False
        self._save_coins(new_list)
        return True
