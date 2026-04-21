"""Тесты CoinService: валидация и обновления монет (active_range/capital)."""

import pytest

from range_program.repositories.coin_repository import CoinRepository
from range_program.services.coin_service import CoinService
from range_program.validation import ValidationError


def test_set_active_requires_existing_coin(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="не найдена"):
        svc.set_active_range("BTC", 1.0, 2.0)


def test_add_coin_rejects_invalid_width_method(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="width_method"):
        svc.add_coin("BTC", width_method="not_a_width")


def test_add_coin_rejects_invalid_center_method(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="center_method"):
        svc.add_coin("BTC", center_method="unknown_center")


def test_set_active_validates_bounds(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    repo.add_coin("BTC")
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="low"):
        svc.set_active_range("BTC", 10.0, 10.0)


def test_add_coin_rejects_invalid_timeframe(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="timeframe"):
        svc.add_coin("BTC", timeframe="bad_tf")


def test_add_coin_rejects_invalid_lookback_days(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="lookback_days"):
        svc.add_coin("BTC", lookback_days=0)


def test_clear_active_range_clears_range(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    ok, _ = svc.add_coin("BTC")
    assert ok
    svc.set_active_range("BTC", 1.0, 2.0, comment="ставим бота")
    cleared = svc.clear_active_range("BTC", comment="сброс вручную")
    assert cleared.active_range is None
