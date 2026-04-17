"""Минимальные тесты интерактивного меню и чистых хелперов."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from range_program.cli import app
from range_program.menu import (
    MenuDeps,
    _do_recalc,
    parse_int_with_default,
    parse_optional_float,
    parse_optional_str,
    prompt_next_step,
)
from range_program.models.coin import Coin
from range_program.models.recommended_range import RecommendedRange
from range_program.repositories.check_history_repository import CheckHistoryRepository
from range_program.repositories.coin_repository import CoinRepository
from range_program.services.check_service import CheckService
from range_program.services.coin_service import CoinService


def test_parse_optional_float() -> None:
    assert parse_optional_float("") is None
    assert parse_optional_float("   ") is None
    assert parse_optional_float("1.25") == 1.25


def test_parse_optional_float_invalid_raises_clear_message() -> None:
    with pytest.raises(ValueError, match="Ожидалось число"):
        parse_optional_float("12abc")


def test_parse_optional_str() -> None:
    assert parse_optional_str("") is None
    assert parse_optional_str("  ") is None
    assert parse_optional_str(" usdt ") == "usdt"


def test_parse_int_with_default() -> None:
    assert parse_int_with_default("", default=10, minimum=1) == 10
    assert parse_int_with_default("5", default=10, minimum=1) == 5


def test_parse_int_with_default_below_minimum_raises() -> None:
    with pytest.raises(ValueError):
        parse_int_with_default("0", default=10, minimum=1)


def test_menu_command_exits_immediately_when_select_returns_exit() -> None:
    runner = CliRunner()
    with patch("range_program.menu.questionary.select") as sel:
        mock_q = MagicMock()
        mock_q.ask.return_value = "exit"
        sel.return_value = mock_q
        result = runner.invoke(app, ["menu"])
    assert result.exit_code == 0
    assert "Выход" in result.output or "интерактивный" in result.output


def test_prompt_next_step_maps_choice() -> None:
    with patch("range_program.menu.questionary.select") as sel:
        mock_q = MagicMock()
        mock_q.ask.return_value = "main"
        sel.return_value = mock_q
        assert prompt_next_step("Test") == "main"


def _dt() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rr() -> RecommendedRange:
    return RecommendedRange(
        low=90.0,
        high=110.0,
        center=100.0,
        width_pct=20.0,
        calculated_at=_dt(),
        center_method="ema",
        width_method="atr",
    )


class _FakeRecalcService:
    def __init__(self, coins: CoinService, *, attach_rr: bool = True) -> None:
        self._coins = coins
        self.attach_rr = attach_rr
        self.calls: list[str] = []

    def recalc(self, symbol: str):  # noqa: ANN001
        sym = Coin.normalize_symbol(symbol)
        self.calls.append(sym)
        coin = self._coins.get_coin(sym)
        assert coin is not None
        if self.attach_rr:
            self._coins.update_coin(replace(coin, recommended_range=_rr()))

        class _Outcome:
            symbol = sym
            mode = coin.mode
            current_price = 100.0
            recommended = _rr()
            center_comparison: tuple = ()
            width_comparison: tuple = ()

        return _Outcome()


def _build_menu_deps(tmp_path, *, attach_rr: bool = True) -> MenuDeps:
    repo = CoinRepository(tmp_path / "coins.json")
    coins = CoinService(repo)
    ok, coin = coins.add_coin("SOL")
    assert ok and coin is not None
    recalc = _FakeRecalcService(coins, attach_rr=attach_rr)
    return MenuDeps(
        coins=coins,
        market=MagicMock(),
        recalc=recalc,  # type: ignore[arg-type]
        check=MagicMock(spec=CheckService),
        history_repo=MagicMock(spec=CheckHistoryRepository),
    )


def test_menu_recalc_save_calls_set_active_with_recommended_bounds(tmp_path) -> None:
    deps = _build_menu_deps(tmp_path)
    with (
        patch("range_program.menu._pick_coin_symbol", return_value="SOL"),
        patch("range_program.menu.questionary.confirm") as confirm,
        patch("range_program.menu.print_recalc_center_comparison_table"),
        patch("range_program.menu.print_recalc_width_comparison_table"),
    ):
        confirm.return_value.ask.return_value = True
        _do_recalc(deps)

    coin = deps.coins.get_coin("SOL")
    assert coin is not None
    assert coin.active_range is not None
    assert coin.active_range.low == 90.0
    assert coin.active_range.high == 110.0


def test_menu_recalc_dont_save_keeps_active_range_unchanged(tmp_path) -> None:
    deps = _build_menu_deps(tmp_path)
    with (
        patch("range_program.menu._pick_coin_symbol", return_value="SOL"),
        patch("range_program.menu.questionary.confirm") as confirm,
        patch("range_program.menu.print_recalc_center_comparison_table"),
        patch("range_program.menu.print_recalc_width_comparison_table"),
    ):
        confirm.return_value.ask.return_value = False
        _do_recalc(deps)

    coin = deps.coins.get_coin("SOL")
    assert coin is not None
    assert coin.active_range is None


def test_menu_recalc_with_missing_recommended_range_does_not_save(tmp_path) -> None:
    deps = _build_menu_deps(tmp_path, attach_rr=False)
    with (
        patch("range_program.menu._pick_coin_symbol", return_value="SOL"),
        patch("range_program.menu.questionary.confirm") as confirm,
        patch("range_program.menu.print_recalc_center_comparison_table"),
        patch("range_program.menu.print_recalc_width_comparison_table"),
    ):
        confirm.return_value.ask.return_value = True
        _do_recalc(deps)

    coin = deps.coins.get_coin("SOL")
    assert coin is not None
    assert coin.recommended_range is None
    assert coin.active_range is None
