import pytest

from range_program.repositories.coin_repository import CoinRepository
from range_program.services.coin_service import CoinService
from range_program.validation import ValidationError


def test_set_active_requires_existing_coin(tmp_path) -> None:
    path = tmp_path / "c.json"
    repo = CoinRepository(path)
    svc = CoinService(repo)
    with pytest.raises(ValidationError, match="not found"):
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
    with pytest.raises(ValidationError, match="low must"):
        svc.set_active_range("BTC", 10.0, 10.0)
