"""
Репозиторий истории проверок (check history).

Файл отвечает за чтение и запись `data/check_history.json`:
- безопасная (атомарная) запись через временный файл + `os.replace`,
- резервная копия `.bak` перед обновлением,
- сохранение повреждённого JSON в `.corrupt.*` для восстановления,
- lock-файл для защиты от одновременной записи несколькими процессами.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from range_program.models.check_result import CheckResult

log = logging.getLogger("range_program.check_history")


def _default_path() -> Path:
    """Путь по умолчанию до `data/check_history.json` в корне проекта."""
    return Path(__file__).resolve().parents[3] / "data" / "check_history.json"


def _parse_dt(value: str) -> datetime:
    """Разобрать ISO-datetime (включая суффикс `Z`) в `datetime`."""
    raw = value.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


class CheckHistoryRepository:
    """
    Репозиторий истории результатов check (`data/check_history.json`).

    Репозиторий ограничивает размер файла (по символу и глобально) и защищает
    запись от повреждений: lock-файл, атомарная замена и backup.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_per_symbol: int = 500,
        max_total: int = 5000,
        lock_timeout_seconds: float = 10.0,
        stale_lock_seconds: float = 60.0,
    ) -> None:
        self._path = path or _default_path()
        self._max_per_symbol = int(max_per_symbol)
        self._max_total = int(max_total)
        self._lock_timeout_seconds = float(lock_timeout_seconds)
        self._stale_lock_seconds = float(stale_lock_seconds)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def max_per_symbol(self) -> int:
        return self._max_per_symbol

    @property
    def max_total(self) -> int:
        return self._max_total

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _lock_path(self) -> Path:
        """Путь до lock-файла для межпроцессной синхронизации записи."""
        return self._path.with_name(f"{self._path.name}.lock")

    def _backup_path(self) -> Path:
        """Путь до резервной копии последнего корректного файла истории."""
        return self._path.with_name(f"{self._path.name}.bak")

    def _corrupt_path(self) -> Path:
        """Путь для сохранения повреждённого JSON (для последующего восстановления)."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return self._path.with_name(f"{self._path.name}.corrupt.{stamp}")

    def _read_text(self) -> str:
        """Прочитать содержимое JSON-файла и нормализовать пробелы."""
        return self._path.read_text(encoding="utf-8").strip()

    def _parse_items(self, text: str) -> list[dict[str, Any]]:
        """Разобрать JSON как список словарей; при неверном формате поднять исключение."""
        if not text:
            return []
        data = json.loads(text)
        if not isinstance(data, list):
            raise TypeError(f"check_history.json must contain a list, got {type(data)!r}")
        return [x for x in data if isinstance(x, dict)]

    def _acquire_lock(self) -> None:
        """Захватить lock-файл (с таймаутом) для защиты записи истории между процессами."""
        self._ensure_parent()
        lock_path = self._lock_path()
        deadline = time.monotonic() + max(self._lock_timeout_seconds, 0.0)
        payload = f"pid={os.getpid()} created_at={datetime.now(timezone.utc).isoformat()}\n"

        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age >= self._stale_lock_seconds:
                    try:
                        lock_path.unlink()
                        log.warning("removed stale history lock: %s", lock_path)
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for history lock: {lock_path}")
                time.sleep(0.05)
                continue

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
            except Exception:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                raise
            return

    def _release_lock(self) -> None:
        """Снять lock-файл (если уже снят, игнорировать)."""
        try:
            self._lock_path().unlink()
        except FileNotFoundError:
            pass

    def _quarantine_corrupt_file(self, raw_text: str, reason: str) -> None:
        """Сохранить повреждённый JSON, затем восстановить из `.bak` или сбросить в `[]`."""
        corrupt_path = self._corrupt_path()
        corrupt_path.write_text(raw_text, encoding="utf-8")
        log.error("check_history.json повреждён, копия сохранена в %s: %s", corrupt_path, reason)

        backup_path = self._backup_path()
        if backup_path.exists():
            shutil.copy2(backup_path, self._path)
            log.warning("check_history.json восстановлен из backup: %s", backup_path)
            return

        self._path.write_text("[]\n", encoding="utf-8")
        log.warning("check_history.json сброшен в пустой список после повреждения")

    def _load_raw_unlocked(self) -> list[dict[str, Any]]:
        self._ensure_parent()
        if not self._path.exists():
            return []
        try:
            return self._parse_items(self._read_text())
        except json.JSONDecodeError as exc:
            self._quarantine_corrupt_file(self._read_text(), str(exc))
            return self._parse_items(self._read_text())
        except TypeError as exc:
            self._quarantine_corrupt_file(self._read_text(), str(exc))
            return self._parse_items(self._read_text())

    def _load_raw(self) -> list[dict[str, Any]]:
        try:
            return self._parse_items(self._read_text())
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, TypeError):
            self._acquire_lock()
            try:
                return self._load_raw_unlocked()
            finally:
                self._release_lock()

    def _save_raw_unlocked(self, items: list[dict[str, Any]]) -> None:
        self._ensure_parent()
        payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._path.with_name(f"{self._path.name}.tmp.{os.getpid()}")
        tmp_path.write_text(payload, encoding="utf-8")
        if self._path.exists():
            shutil.copy2(self._path, self._backup_path())
        os.replace(tmp_path, self._path)

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
        items: list[dict[str, Any]]
        self._acquire_lock()
        try:
            items = self._load_raw_unlocked()
            items.append(self._check_result_to_record(result))
            items = self._rotate(items)
            items = self._apply_global_limit(items)
            self._save_raw_unlocked(items)
        finally:
            self._release_lock()

    def _rotate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limit = int(self._max_per_symbol)
        if limit < 1:
            return []
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
            entries_sorted = sorted(entries, key=lambda t: (t[0], t[1]))
            drop = entries_sorted[: len(entries_sorted) - limit]
            for _, idx in drop:
                to_drop.add(idx)
            log.info("history rotate symbol=%s drop=%s keep=%s", sym, len(drop), limit)

        if not to_drop:
            return items
        return [rec for idx, rec in enumerate(items) if idx not in to_drop]

    def _apply_global_limit(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limit = int(self._max_total)
        if limit < 1:
            return []
        if len(items) <= limit:
            return items

        def key(d: dict[str, Any]) -> datetime:
            try:
                dt = _parse_dt(str(d.get("checked_at", "")))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return datetime.min.replace(tzinfo=timezone.utc)

        indexed = [(key(rec), idx) for idx, rec in enumerate(items)]
        indexed_sorted = sorted(indexed, key=lambda t: (t[0], t[1]))
        to_drop = {idx for _, idx in indexed_sorted[: len(indexed_sorted) - limit]}
        log.info("history rotate global drop=%s keep=%s", len(to_drop), limit)
        return [rec for idx, rec in enumerate(items) if idx not in to_drop]

    def purge_older_than_days(self, days: int, *, now_utc: datetime | None = None) -> int:
        n = int(days)
        if n < 1:
            return 0
        now = now_utc or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=n)
        items = self._load_raw()
        before = len(items)

        def keep(rec: dict[str, Any]) -> bool:
            try:
                dt = _parse_dt(str(rec.get("checked_at", "")))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return True
            return dt >= cutoff

        kept = [rec for rec in items if keep(rec)]
        removed = before - len(kept)
        if removed:
            log.info("history purge older-than-days=%s removed=%s", n, removed)
            self._acquire_lock()
            try:
                self._save_raw_unlocked(kept)
            finally:
                self._release_lock()
        return removed

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._load_raw())

    def get_history(self, symbol: str) -> list[dict[str, Any]]:
        sym = symbol.strip().upper()
        return [x for x in self._load_raw() if str(x.get("symbol", "")).upper() == sym]

    def get_last_n(self, symbol: str, n: int) -> list[dict[str, Any]]:
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
