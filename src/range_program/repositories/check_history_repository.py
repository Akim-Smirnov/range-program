from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from range_program.models.check_result import CheckResult

log = logging.getLogger("range_program.check_history")


def _default_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "check_history.json"


def _parse_dt(value: str) -> datetime:
    raw = value.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


class CheckHistoryRepository:
    """Append-only JSON-история проверок (`data/check_history.json`)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_path()

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_raw(self) -> list[dict[str, Any]]:
        self._ensure_parent()
        if not self._path.exists():
            return []
        text = self._path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            log.error("check_history.json повреждён, начинаем с пустого списка: %s", e)
            return []
        if not isinstance(data, list):
            log.error("check_history.json должен быть массивом, получено %s", type(data))
            return []
        return [x for x in data if isinstance(x, dict)]

    def _save_raw(self, items: list[dict[str, Any]]) -> None:
        self._ensure_parent()
        self._path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _check_result_to_record(r: CheckResult) -> dict[str, Any]:
        return {
            "symbol": r.symbol,
            "current_price": r.current_price,
            "active_low": r.active_low,
            "active_high": r.active_high,
            "recommended_low": r.recommended_low,
            "recommended_high": r.recommended_high,
            "status": r.status,
            "recommendation": r.recommendation,
            "deviation_from_center_pct": r.deviation_from_active_center_pct,
            "distance_to_lower_pct": r.distance_to_lower_pct,
            "distance_to_upper_pct": r.distance_to_upper_pct,
            "checked_at": r.checked_at.isoformat(),
        }

    def save_check(self, result: CheckResult) -> None:
        """Добавить запись в конец истории (не затирая прошлые)."""
        items = self._load_raw()
        items.append(self._check_result_to_record(result))
        self._save_raw(items)

    def get_all(self) -> list[dict[str, Any]]:
        """Все записи в порядке хранения в файле."""
        return list(self._load_raw())

    def get_history(self, symbol: str) -> list[dict[str, Any]]:
        """Все записи по символу (порядок как в файле — обычно по времени добавления)."""
        sym = symbol.strip().upper()
        return [x for x in self._load_raw() if str(x.get("symbol", "")).upper() == sym]

    def get_last_n(self, symbol: str, n: int) -> list[dict[str, Any]]:
        """Последние n записей по монете, от новых к старым."""
        if n < 1:
            return []
        rows = self.get_history(symbol)

        def key(d: dict[str, Any]) -> datetime:
            try:
                return _parse_dt(str(d["checked_at"]))
            except (KeyError, ValueError):
                return datetime.min

        rows_sorted = sorted(rows, key=key, reverse=True)
        return rows_sorted[:n]

    def get_global_last_n(self, n: int) -> list[dict[str, Any]]:
        """Последние n записей по всем монетам (по времени checked_at)."""
        if n < 1:
            return []
        all_rows = self._load_raw()

        def key(d: dict[str, Any]) -> datetime:
            try:
                return _parse_dt(str(d["checked_at"]))
            except (KeyError, ValueError):
                return datetime.min

        sorted_rows = sorted(all_rows, key=key, reverse=True)
        return sorted_rows[:n]
