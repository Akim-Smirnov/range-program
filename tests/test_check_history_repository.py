"""Тесты CheckHistoryRepository (JSON, отсутствующий/пустой/битый файл)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from range_program.models.check_result import CheckResult
from range_program.repositories.check_history_repository import CheckHistoryRepository


def _sample_result(symbol: str = "BTC", checked_at: datetime | None = None) -> CheckResult:
    t = checked_at or datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)
    return CheckResult(
        symbol=symbol,
        current_price=68000.0,
        active_low=60000.0,
        active_high=70000.0,
        active_center=65000.0,
        recommended_low=61000.0,
        recommended_high=71000.0,
        recommended_center=66000.0,
        distance_to_lower_pct=5.0,
        distance_to_upper_pct=4.0,
        deviation_from_active_center_pct=3.0,
        status="OK",
        recommendation="hold",
        checked_at=t,
    )


@pytest.fixture
def hist_path(tmp_path: Path) -> Path:
    return tmp_path / "check_history.json"


def test_missing_file_empty_lists(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path)
    assert repo.get_all() == []
    assert repo.get_history("BTC") == []
    assert repo.get_last_n("BTC", 5) == []
    assert repo.get_global_last_n(10) == []


def test_save_and_append(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path)
    r1 = _sample_result("BTC", datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc))
    r2 = _sample_result("BTC", datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc))
    repo.save_check(r1)
    repo.save_check(r2)
    all_rows = repo.get_all()
    assert len(all_rows) == 2
    assert all_rows[0]["symbol"] == "BTC"
    assert all_rows[0]["deviation_from_center_pct"] == 3.0
    assert all_rows[1]["checked_at"] == r2.checked_at.isoformat()
    assert hist_path.with_name("check_history.json.bak").exists()


def test_get_last_n_newest_first(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path)
    repo.save_check(_sample_result("ETH", datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("ETH", datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("ETH", datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)))
    last = repo.get_last_n("ETH", 2)
    assert [x["checked_at"] for x in last] == [
        datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc).isoformat(),
    ]


def test_get_global_last_n(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path)
    repo.save_check(_sample_result("BTC", datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("ETH", datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)))
    g = repo.get_global_last_n(1)
    assert len(g) == 1
    assert g[0]["symbol"] == "ETH"


def test_corrupt_json_treated_as_empty(hist_path: Path) -> None:
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text("{not json", encoding="utf-8")
    repo = CheckHistoryRepository(hist_path)
    assert repo.get_all() == []
    corrupt_files = list(hist_path.parent.glob("check_history.json.corrupt.*"))
    assert len(corrupt_files) == 1
    assert corrupt_files[0].read_text(encoding="utf-8") == "{not json"
    repo.save_check(_sample_result())
    assert len(repo.get_all()) == 1
    data = json.loads(hist_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)


def test_empty_file(hist_path: Path) -> None:
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text("   \n", encoding="utf-8")
    repo = CheckHistoryRepository(hist_path)
    assert repo.get_all() == []


def test_rotation_limits_history_per_symbol(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path, max_per_symbol=3)
    for i in range(5):
        repo.save_check(_sample_result("BTC", datetime(2026, 4, 10 + i, 12, 0, tzinfo=timezone.utc)))
    rows = repo.get_history("BTC")
    assert len(rows) == 3
    # Должны остаться самые новые три
    assert [r["checked_at"] for r in repo.get_last_n("BTC", 10)] == [
        datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc).isoformat(),
    ]


def test_global_limit_applies(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path, max_per_symbol=999, max_total=3)
    repo.save_check(_sample_result("BTC", datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("ETH", datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("SOL", datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("XRP", datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)))
    all_rows = repo.get_all()
    assert len(all_rows) == 3
    assert {r["symbol"] for r in all_rows} == {"ETH", "SOL", "XRP"}


def test_purge_older_than_days(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path, max_per_symbol=999, max_total=999)
    repo.save_check(_sample_result("BTC", datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)))
    repo.save_check(_sample_result("BTC", datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)))
    removed = repo.purge_older_than_days(7, now_utc=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc))
    assert removed == 1
    rows = repo.get_history("BTC")
    assert len(rows) == 1
    assert rows[0]["checked_at"] == datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc).isoformat()


def test_restore_from_backup_when_main_file_is_corrupt(hist_path: Path) -> None:
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text("{broken", encoding="utf-8")
    hist_path.with_name("check_history.json.bak").write_text(
        json.dumps([{"symbol": "SOL", "checked_at": "2026-04-12T00:00:00+00:00"}]),
        encoding="utf-8",
    )
    repo = CheckHistoryRepository(hist_path)
    rows = repo.get_all()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "SOL"


def test_stale_lock_is_removed_before_write(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path, stale_lock_seconds=0.0)
    lock_path = hist_path.with_name("check_history.json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("stale", encoding="utf-8")
    repo.save_check(_sample_result())
    assert not lock_path.exists()
    assert len(repo.get_all()) == 1


def test_timeout_when_active_lock_cannot_be_acquired(hist_path: Path) -> None:
    repo = CheckHistoryRepository(hist_path, lock_timeout_seconds=0.0, stale_lock_seconds=9999.0)
    lock_path = hist_path.with_name("check_history.json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("busy", encoding="utf-8")
    with pytest.raises(TimeoutError):
        repo.save_check(_sample_result())
