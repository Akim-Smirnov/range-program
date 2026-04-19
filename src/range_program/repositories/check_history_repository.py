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

    def __init__(self, path: Path | None = None, *, max_per_symbol: int = 500) -> None:
        self._path = path or _default_path()
        self._max_per_symbol = int(max_per_symbol)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def max_per_symbol(self) -> int:
        """Максимум записей на монету (защита от бесконечного роста файла)."""
        return self._max_per_symbol

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
        """Добавить запись в конец истории и применить ротацию по символу."""
        items = self._load_raw()
        items.append(self._check_result_to_record(result))
        items = self._rotate(items)
        self._save_raw(items)

    def _rotate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ограничить число записей на монету до `max_per_symbol`, удаляя самые старые.

        Важно: сохраняем порядок оставшихся записей как в файле.
        """
        limit = int(self._max_per_symbol)
        if limit < 1:
            return []
        # Собираем индексы записей по символам.
        by_symbol: dict[str, list[tuple[datetime, int]]] = {}
        for idx, rec in enumerate(items):
            sym = str(rec.get("symbol", "")).strip().upper()
            if not sym:
                continue
            try:
                dt = _parse_dt(str(rec.get("checked_at", "")))
            except (ValueError, TypeError):
                dt = datetime.min
            by_symbol.setdefault(sym, []).append((dt, idx))

        to_drop: set[int] = set()
        for sym, entries in by_symbol.items():
            if len(entries) <= limit:
                continue
            # Сортируем от самых старых к новым; при равенстве — по позиции в файле.
            entries_sorted = sorted(entries, key=lambda t: (t[0], t[1]))
            drop = entries_sorted[: len(entries_sorted) - limit]
            for _, idx in drop:
                to_drop.add(idx)
            log.info("history rotate symbol=%s drop=%s keep=%s", sym, len(drop), limit)

        if not to_drop:
            return items
        return [rec for idx, rec in enumerate(items) if idx not in to_drop]

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
