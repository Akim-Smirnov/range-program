"""Тесты CoinRepository: чтение/запись `coins.json`, миграции формата и ошибки данных."""

import json
from pathlib import Path

import pytest

from range_program.models.coin import Coin
from range_program.models.defaults import DEFAULT_MODE, DEFAULT_TIMEFRAME
from range_program.repositories.coin_repository import CoinRepository


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    return tmp_path / "coins.json"


def test_add_list_remove(repo_path: Path) -> None:
    repo = CoinRepository(repo_path)
    assert repo.list_coins() == []

    assert repo.add_coin("btc") is True
    assert repo.add_coin("BTC") is False

    coins = repo.list_coins()
    assert len(coins) == 1
    assert coins[0].symbol == "BTC"
    assert coins[0].mode == DEFAULT_MODE
    assert coins[0].timeframe == DEFAULT_TIMEFRAME

    assert repo.add_coin("eth") is True
    assert len(repo.list_coins()) == 2

    assert repo.remove_coin("btc") is True
    assert repo.remove_coin("btc") is False
    assert len(repo.list_coins()) == 1


def test_json_roundtrip(repo_path: Path) -> None:
    repo = CoinRepository(repo_path)
    assert repo.add_coin("SOL") is True

    text = repo_path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, list)
    assert data[0]["symbol"] == "SOL"
    assert "created_at" in data[0]
    assert data[0]["mode"] == DEFAULT_MODE
    assert data[0]["active_range"] is None


def test_legacy_record_merged(repo_path: Path) -> None:
    legacy = [
        {
            "symbol": "xrp",
            "created_at": "2025-01-01T12:00:00+00:00",
        }
    ]
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.write_text(json.dumps(legacy), encoding="utf-8")

    repo = CoinRepository(repo_path)
    coins = repo.list_coins()
    assert len(coins) == 1
    c = coins[0]
    assert c.symbol == "XRP"
    assert c.mode == DEFAULT_MODE
    assert c.timeframe == DEFAULT_TIMEFRAME


def test_coin_market_fields_roundtrip(repo_path: Path) -> None:
    """Новые поля Coin (биржа, quote, resolved) сериализуются и читаются."""
    from dataclasses import replace
    from datetime import datetime, timezone

    repo = CoinRepository(repo_path)
    assert repo.add_coin("HYPE", exchange="bybit", quote_asset="USDT") is True
    c = repo.get_coin("HYPE")
    assert c is not None
    assert c.exchange == "bybit"
    assert c.quote_asset == "USDT"
    ra = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    updated = replace(
        c,
        resolved_exchange="bybit",
        resolved_symbol_pair="HYPE/USDT",
        resolved_at=ra,
        updated_at=ra,
    )
    assert repo.update_coin(updated) is True
    repo2 = CoinRepository(repo_path)
    again = repo2.get_coin("HYPE")
    assert again is not None
    assert again.resolved_exchange == "bybit"
    assert again.resolved_symbol_pair == "HYPE/USDT"
    assert again.resolved_at == ra


def test_update_coin(repo_path: Path) -> None:
    repo = CoinRepository(repo_path)
    repo.add_coin("BTC", mode="balanced")
    c = repo.get_coin("BTC")
    assert c is not None
    from dataclasses import replace
    from datetime import datetime, timezone

    new_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    updated = replace(c, mode="aggressive", updated_at=new_updated)
    assert repo.update_coin(updated) is True
    again = repo.get_coin("BTC")
    assert again is not None
    assert again.mode == "aggressive"
    assert again.updated_at == new_updated


def test_invalid_json_raises(repo_path: Path) -> None:
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.write_text("{not json", encoding="utf-8")
    repo = CoinRepository(repo_path)
    with pytest.raises(ValueError, match="valid JSON"):
        repo.list_coins()
