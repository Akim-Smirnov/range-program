from __future__ import annotations

import sys

import typer

from range_program.logging_config import get_logger, setup_logging
from range_program.repositories.check_history_repository import CheckHistoryRepository
from range_program.services.check_service import CheckService
from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataService
from range_program.services.recalc_service import RecalcService

setup_logging()
log = get_logger("cli")

app = typer.Typer(help="Range Program — интерактивное меню управления сеточными ботами")
_service = CoinService()
_market = MarketDataService()
_recalc = RecalcService(_service, _market)
_history_repo = CheckHistoryRepository()
_check = CheckService(_service, _market, _recalc, history=_history_repo)


@app.callback(invoke_without_command=True)
def _cli_root(ctx: typer.Context) -> None:
    """Логирует подкоманду; без подкоманды запускает интерактивное меню."""
    if ctx.invoked_subcommand is None:
        _run_interactive_menu()
        return
    log.info("invoke %s argv=%s", ctx.invoked_subcommand, " ".join(sys.argv[1:]))


def _run_interactive_menu() -> None:
    """Запускает интерактивное меню с текущим набором сервисов."""
    from range_program.menu import MenuDeps, run_interactive_menu

    run_interactive_menu(
        MenuDeps(
            coins=_service,
            market=_market,
            recalc=_recalc,
            check=_check,
            history_repo=_history_repo,
        )
    )


@app.command("menu", help="Интерактивное меню (стрелки и Enter).")
def cmd_menu() -> None:
    """Открывает интерактивное меню управления."""
    _run_interactive_menu()


@app.command("ui", help="То же, что menu: интерактивный режим.")
def cmd_ui() -> None:
    """Псевдоним команды menu для запуска интерактивного режима."""
    _run_interactive_menu()


def main() -> None:
    """Точка входа для запуска CLI как функции."""
    app()


if __name__ == "__main__":
    main()
