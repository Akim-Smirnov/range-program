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
    repo.save_check(_sample_result())
    assert len(repo.get_all()) == 1
    data = json.loads(hist_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)


def test_empty_file(hist_path: Path) -> None:
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text("   \n", encoding="utf-8")
    repo = CheckHistoryRepository(hist_path)
    assert repo.get_all() == []
