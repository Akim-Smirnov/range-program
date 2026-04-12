from unittest.mock import patch

from typer.testing import CliRunner

from range_program.cli import app
from range_program.models.coin import Coin
from range_program.models.market_symbol_match import MarketSymbolMatch


def test_resolve_market_command_updates_coin() -> None:
    runner = CliRunner()
    coin = Coin.create("HYPE")
    mm = MarketSymbolMatch(exchange="bybit", symbol_pair="HYPE/USDT", quote_asset="USDT")

    with patch("range_program.cli._service") as svc, patch("range_program.cli._market") as market:
        svc.get_coin.return_value = coin
        market.resolve_market.return_value = mm
        svc.update_coin.return_value = True

        result = runner.invoke(app, ["resolve-market", "HYPE"])

    assert result.exit_code == 0
    assert "Resolved exchange: bybit" in result.output
    assert "Resolved pair: HYPE/USDT" in result.output
    assert "Quote asset: USDT" in result.output
    assert svc.update_coin.called
    args_coin = svc.update_coin.call_args[0][0]
    assert args_coin.resolved_exchange == "bybit"
    assert args_coin.resolved_symbol_pair == "HYPE/USDT"
    assert args_coin.resolved_at is not None
