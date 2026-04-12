"""Минимальные тесты интерактивного меню и чистых хелперов."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from range_program.cli import app
from range_program.menu import parse_int_with_default, parse_optional_float, parse_optional_str, prompt_next_step


def test_parse_optional_float() -> None:
    assert parse_optional_float("") is None
    assert parse_optional_float("   ") is None
    assert parse_optional_float("1.25") == 1.25


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
