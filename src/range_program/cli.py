from __future__ import annotations

import json
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


@app.callback(invoke_without_command=True)
def _cli_root(ctx: typer.Context) -> None:
    """Логирует подкоманду; без подкоманды запускает интерактивное меню."""
    if ctx.invoked_subcommand is None:
        log.info("invoke menu (default) argv=%s", " ".join(sys.argv[1:]))
        _run_interactive_menu()
        return
    log.info("invoke %s argv=%s", ctx.invoked_subcommand, " ".join(sys.argv[1:]))


def _run_interactive_menu() -> None:
    """Запускает интерактивное меню с текущим набором сервисов."""
    try:
        from range_program.menu import MenuDeps, run_interactive_menu
    except ModuleNotFoundError as e:
        log.exception("failed to import interactive menu")
        typer.secho("Не удалось запустить интерактивное меню: не хватает зависимостей.", fg=typer.colors.RED)
        typer.secho(
            "Подсказка: установите зависимости проекта (например: pip install -e .).",
            fg=typer.colors.YELLOW,
        )
        typer.secho(f"Детали: {e}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    try:
        coins = CoinService()
        market = MarketDataService()
        recalc = RecalcService(coins, market)
        history_repo = CheckHistoryRepository()
        check = CheckService(coins, market, recalc, history=history_repo)
    except (json.JSONDecodeError, ValueError, FileNotFoundError, PermissionError) as e:
        log.exception("failed to initialize services (data may be corrupted)")
        typer.secho("Не удалось прочитать локальные данные из папки data/ (возможна поломка JSON).", fg=typer.colors.RED)
        typer.secho(
            "Подсказка: проверьте файлы data/coins.json и data/check_history.json (или восстановите из бэкапа).",
            fg=typer.colors.YELLOW,
        )
        typer.secho(f"Детали: {e}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    except Exception as e:
        log.exception("failed to initialize services")
        typer.secho("Не удалось инициализировать интерактивное меню.", fg=typer.colors.RED)
        typer.secho(f"Детали: {e}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    log.info("start interactive menu")

    try:
        run_interactive_menu(
            MenuDeps(
                coins=coins,
                market=market,
                recalc=recalc,
                check=check,
                history_repo=history_repo,
            )
        )
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("Выход.")
        raise typer.Exit(code=0)
    except Exception as e:
        log.exception("interactive menu crashed")
        typer.secho("Меню завершилось с ошибкой.", fg=typer.colors.RED)
        typer.secho(f"Детали: {e}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)


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
