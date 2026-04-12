from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone

import typer

from range_program.config import DEFAULT_QUOTE_ASSET
from range_program.logging_config import get_logger, setup_logging
from range_program.models.coin import Coin
from range_program.display_helpers import (
    print_grid_setups_block,
    print_mode_comparison_table,
    print_recalc_center_comparison_table,
    print_recalc_width_comparison_table,
)
from range_program.models.defaults import (
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)
from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.range_engine import RangeEngineError
from range_program.services.backtest import run_backtest
from range_program.services.optimizer import best_mode_result, compare_modes
from range_program.services.recalc_service import RecalcService, bars_per_day
from range_program.services.check_service import CheckService
from range_program.validation import ValidationError
from range_program.check_all_report import aggregate_counts, print_check_all_table, print_summary
from range_program.repositories.check_history_repository import CheckHistoryRepository
from range_program.history_view import print_history_entries

setup_logging()
log = get_logger("cli")

app = typer.Typer(help="Range Program — управление монетами для сеточных ботов")
_service = CoinService()
_market = MarketDataService()
_recalc = RecalcService(_service, _market)
_history_repo = CheckHistoryRepository()
_check = CheckService(_service, _market, _recalc, history=_history_repo)


@app.callback()
def _cli_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand:
        log.info("invoke %s argv=%s", ctx.invoked_subcommand, " ".join(sys.argv[1:]))


def _handle_validation(e: ValidationError) -> None:
    typer.secho(str(e), fg=typer.colors.RED)
    raise typer.Exit(code=1)


def _handle_market(e: MarketDataError) -> None:
    typer.secho(str(e), fg=typer.colors.RED)
    raise typer.Exit(code=1)


@app.command("add")
def cmd_add(
    symbol: str = typer.Argument(..., help="Тикер монеты, например BTC"),
    mode: str = typer.Option(DEFAULT_MODE, "--mode", "-m", help="conservative | balanced | aggressive"),
    timeframe: str = typer.Option(DEFAULT_TIMEFRAME, "--timeframe", "-t", help='Таймфрейм, например "4h"'),
    lookback: int = typer.Option(DEFAULT_LOOKBACK_DAYS, "--lookback", "-l", help="Глубина истории в днях"),
    center_method: str = typer.Option(
        DEFAULT_CENTER_METHOD,
        "--center-method",
        help="Метод центра: price, ema, sma, median, midpoint, donchian",
    ),
    width_method: str = typer.Option(
        DEFAULT_WIDTH_METHOD,
        "--width-method",
        help="Метод ширины: atr, std, donchian, historical_range",
    ),
    capital: float | None = typer.Option(
        None,
        "--capital",
        help=f"Капитал в {DEFAULT_QUOTE_ASSET} для расчёта вариантов сетки после recalc (опционально)",
    ),
    exchange: str | None = typer.Option(
        None,
        "--exchange",
        "-e",
        help="Предпочтительная биржа (ccxt id), например bybit; иначе общий fallback",
    ),
    quote: str | None = typer.Option(
        None,
        "--quote",
        "-q",
        help="Предпочтительный котируемый актив (USDT, USDC, …); иначе fallback USDT/USDC/USD",
    ),
) -> None:
    """Добавить монету в список."""
    norm = Coin.normalize_symbol(symbol)
    try:
        ok, coin = _service.add_coin(
            symbol,
            mode=mode,
            timeframe=timeframe,
            lookback_days=lookback,
            center_method=center_method,
            width_method=width_method,
            capital=capital,
            exchange=exchange,
            quote_asset=quote,
        )
    except ValidationError as e:
        _handle_validation(e)
        return
    if not ok:
        typer.secho(f"Монета {norm} уже есть.", fg=typer.colors.YELLOW)
        return
    assert coin is not None
    log.info("add symbol=%s mode=%s", norm, coin.mode)
    typer.echo(f"Добавлено: {coin.symbol} (создана {coin.created_at.isoformat()})")


@app.command("remove")
def cmd_remove(symbol: str = typer.Argument(..., help="Тикер монеты")) -> None:
    """Удалить монету из списка."""
    norm = Coin.normalize_symbol(symbol)
    if not _service.remove_coin(symbol):
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    log.info("remove symbol=%s", norm)
    typer.echo(f"Удалено: {norm}")


@app.command("list")
def cmd_list() -> None:
    """Показать все монеты."""
    coins = _service.list_coins()
    if not coins:
        typer.echo("(список пуст)")
        return
    for c in sorted(coins, key=lambda x: x.symbol):
        cap = "—" if c.capital is None else str(c.capital)
        typer.echo(
            f"{c.symbol}\t{c.mode}\t{c.timeframe}\tlookback={c.lookback_days}\tcapital={cap}\t{c.updated_at.isoformat()}"
        )


@app.command("show")
def cmd_show(symbol: str = typer.Argument(..., help="Тикер монеты")) -> None:
    """Показать одну монету (параметры и активный диапазон, если задан)."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    typer.echo(f"symbol:         {coin.symbol}")
    typer.echo(f"mode:           {coin.mode}")
    typer.echo(f"timeframe:      {coin.timeframe}")
    typer.echo(f"lookback_days:  {coin.lookback_days}")
    typer.echo(f"center_method:  {coin.center_method}")
    typer.echo(f"width_method:   {coin.width_method}")
    typer.echo(f"created_at:     {coin.created_at.isoformat()}")
    typer.echo(f"updated_at:     {coin.updated_at.isoformat()}")
    if coin.capital is None:
        typer.echo(f"capital:        (none)")
    else:
        typer.echo(f"capital:        {coin.capital} {DEFAULT_QUOTE_ASSET}")
    typer.echo(f"preferred exchange: {coin.exchange or '(none)'}")
    typer.echo(f"preferred quote:    {coin.quote_asset or '(none)'}")
    typer.echo(f"resolved exchange:  {coin.resolved_exchange or '(none)'}")
    typer.echo(f"resolved pair:      {coin.resolved_symbol_pair or '(none)'}")
    if coin.resolved_at is None:
        typer.echo(f"resolved at:        (none)")
    else:
        typer.echo(f"resolved at:        {coin.resolved_at.isoformat()}")
    if coin.active_range is None:
        typer.echo("active_range:   (none)")
    else:
        ar = coin.active_range
        typer.echo("active_range:")
        typer.echo(f"  low:     {ar.low}")
        typer.echo(f"  high:    {ar.high}")
        typer.echo(f"  set_at:  {ar.set_at.isoformat()}")
        if ar.comment is not None:
            typer.echo(f"  comment: {ar.comment}")

    if coin.recommended_range is None:
        typer.echo("recommended_range: (none)")
    else:
        rr = coin.recommended_range
        typer.echo("recommended_range:")
        typer.echo(f"  low:           {rr.low}")
        typer.echo(f"  high:          {rr.high}")
        typer.echo(f"  center:        {rr.center}")
        typer.echo(f"  width_pct:     {rr.width_pct}")
        typer.echo(f"  calculated_at: {rr.calculated_at.isoformat()}")
        typer.echo(f"  center_method: {rr.center_method}")
        typer.echo(f"  width_method:  {rr.width_method}")
        if rr.grid_configs:
            typer.echo("Recommended grid setups:")
            for g in rr.grid_configs:
                typer.echo(
                    f"  - {g.mode}: {g.grid_count} grids, {g.step_pct:.2f}%, {g.order_size:.2f} {DEFAULT_QUOTE_ASSET}/order"
                )

    if coin.last_check is None:
        typer.echo("last_status:      (none)")
        typer.echo("last_checked_at:  (none)")
        typer.echo("last_check:       (none)")
    else:
        lc = coin.last_check
        typer.echo(f"last_status:      {lc.status}")
        typer.echo(f"last_checked_at:  {lc.checked_at.isoformat()}")
        typer.echo("last_check:")
        typer.echo(f"  recommendation: {lc.recommendation}")

    try:
        quote = _market.get_price_quote(norm, coin=coin)
        typer.echo(f"last_price:     {quote.price}")
        typer.echo(f"price_as_of:    {quote.as_of.isoformat()}")
    except MarketDataError as e:
        typer.secho(f"market:         не удалось получить цену ({e})", fg=typer.colors.YELLOW)


@app.command("price")
def cmd_price(symbol: str = typer.Argument(..., help="Тикер базового актива, например BTC")) -> None:
    """Текущая цена; если монета в списке — fallback по биржам/котировкам, иначе Binance+USDT."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    try:
        q = _market.get_price_quote(norm, coin=coin)
    except MarketDataError as e:
        _handle_market(e)
        return
    pair = _market.pair_for_symbol(norm, coin=coin)
    typer.echo(f"{norm}\t{pair}\t{q.price}\t{q.as_of.isoformat()}")


@app.command("candles")
def cmd_candles(
    symbol: str = typer.Argument(..., help="Тикер монеты из локального списка"),
    limit: int = typer.Option(10, "--limit", "-n", help="Число последних свечей"),
) -> None:
    """Последние свечи; таймфрейм берётся из настроек монеты в хранилище."""
    if limit < 1:
        typer.secho("Параметр --limit должен быть не меньше 1.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище. Сначала: range add {norm}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    try:
        candles = _market.get_ohlcv(norm, coin.timeframe, limit, coin=coin)
    except MarketDataError as e:
        _handle_market(e)
        return
    typer.echo(f"pair={_market.pair_for_symbol(norm, coin=coin)} timeframe={coin.timeframe} limit={len(candles)}")
    typer.echo("time(UTC)\topen\thigh\tlow\tclose\tvolume")
    for bar in candles:
        typer.echo(
            f"{bar.timestamp.isoformat()}\t{bar.open}\t{bar.high}\t{bar.low}\t{bar.close}\t{bar.volume}"
        )


@app.command("resolve-market")
def cmd_resolve_market(
    symbol: str = typer.Argument(..., help="Тикер монеты из хранилища"),
) -> None:
    """Найти рабочий рынок (биржа + пара) и сохранить в монету (resolved_*)."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    try:
        m = _market.resolve_market(coin)
    except MarketDataError as e:
        _handle_market(e)
        return
    now = datetime.now(timezone.utc)
    updated = replace(
        coin,
        resolved_exchange=m.exchange,
        resolved_symbol_pair=m.symbol_pair,
        resolved_at=now,
        updated_at=now,
    )
    if not _service.update_coin(updated):
        typer.secho("Не удалось сохранить монету.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    log.info("resolve-market symbol=%s exchange=%s pair=%s", norm, m.exchange, m.symbol_pair)
    typer.echo("")
    typer.echo(f"Symbol: {norm}")
    typer.echo(f"Resolved exchange: {m.exchange}")
    typer.echo(f"Resolved pair: {m.symbol_pair}")
    typer.echo(f"Quote asset: {m.quote_asset}")


@app.command("recalc")
def cmd_recalc(symbol: str = typer.Argument(..., help="Тикер монеты из хранилища")) -> None:
    """Пересчитать рекомендуемый диапазон и сохранить в монету; вывести сравнение center_method и width_method."""
    norm = Coin.normalize_symbol(symbol)
    coin_before = _service.get_coin(norm)
    try:
        out = _recalc.recalc(symbol)
    except ValidationError as e:
        _handle_validation(e)
    except (MarketDataError, RangeEngineError) as e:
        log.warning("recalc failed symbol=%s: %s", symbol, e)
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    rr = out.recommended
    log.info("recalc symbol=%s center=%s", out.symbol, rr.center)
    typer.echo("")
    typer.echo(f"{out.symbol}")
    typer.echo(f"Current price: {out.current_price}")
    typer.echo(f"Range: {rr.low:g} - {rr.high:g}")
    typer.echo(f"Center: {rr.center:g}")
    typer.echo(f"Width: {rr.width_pct:g}%")
    typer.echo(f"Mode: {out.mode}")
    typer.echo(f"center_method:    {rr.center_method}")
    typer.echo(f"width_method:     {rr.width_method}")
    typer.echo(f"calculated_at:    {rr.calculated_at.isoformat()}")

    print_recalc_center_comparison_table(out.center_comparison, saved_center_method=rr.center_method)
    print_recalc_width_comparison_table(out.width_comparison, saved_width_method=rr.width_method)

    cap = coin_before.capital if coin_before is not None else None
    if cap is not None and rr.grid_configs:
        print_grid_setups_block(rr.grid_configs, quote=DEFAULT_QUOTE_ASSET)
    elif cap is None:
        typer.echo("")
        typer.secho(
            "Capital not set; grid setups are not available. Use: range set-capital SYMBOL AMOUNT",
            fg=typer.colors.YELLOW,
        )


@app.command("set-capital")
def cmd_set_capital(
    symbol: str = typer.Argument(..., help="Тикер монеты из хранилища"),
    amount: float = typer.Argument(..., help=f"Капитал в {DEFAULT_QUOTE_ASSET}"),
) -> None:
    """Задать капитал для монеты (для расчёта вариантов сетки при recalc)."""
    try:
        coin = _service.set_capital(symbol, amount)
    except ValidationError as e:
        _handle_validation(e)
        return
    log.info("set-capital symbol=%s amount=%s", coin.symbol, amount)
    typer.echo(f"capital для {coin.symbol} установлен: {amount} {DEFAULT_QUOTE_ASSET}")


@app.command("clear-capital")
def cmd_clear_capital(symbol: str = typer.Argument(..., help="Тикер монеты из хранилища")) -> None:
    """Сбросить капитал монеты (сетки после recalc не считаются)."""
    try:
        coin = _service.clear_capital(symbol)
    except ValidationError as e:
        _handle_validation(e)
        return
    log.info("clear-capital symbol=%s", coin.symbol)
    typer.echo(f"capital для {coin.symbol} сброшен.")


@app.command("check")
def cmd_check(
    symbol: str | None = typer.Argument(default=None, help="Тикер монеты (не используйте вместе с --all)"),
    all_coins: bool = typer.Option(False, "--all", "-a", help="Проверить все монеты из хранилища"),
) -> None:
    """Оценить активный диапазон (одна монета или --all: таблица + сводка)."""
    if all_coins and symbol:
        typer.secho("Укажите либо SYMBOL, либо --all.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if all_coins:
        log.info("check --all")
        rows = _check.run_check_all()
        print_check_all_table(rows)
        print_summary(aggregate_counts(rows))
        log.info("check --all done rows=%d", len(rows))
        return
    if not symbol:
        typer.secho("Укажите тикер монеты или опцию --all.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        r = _check.run_check(symbol)
    except ValidationError as e:
        _handle_validation(e)
        return
    log.info("check symbol=%s status=%s", r.symbol, r.status)
    typer.echo(f"symbol:                        {r.symbol}")
    typer.echo(f"current_price:                 {r.current_price}")
    typer.echo(f"active_low:                    {r.active_low}")
    typer.echo(f"active_high:                   {r.active_high}")
    typer.echo(f"active_center:                 {r.active_center}")
    typer.echo(f"recommended_low:               {r.recommended_low}")
    typer.echo(f"recommended_high:              {r.recommended_high}")
    typer.echo(f"recommended_center:            {r.recommended_center}")
    typer.echo(f"distance_to_lower_pct:         {r.distance_to_lower_pct}")
    typer.echo(f"distance_to_upper_pct:         {r.distance_to_upper_pct}")
    typer.echo(f"deviation_from_active_center_pct: {r.deviation_from_active_center_pct}")
    typer.echo(f"status:                        {r.status}")
    typer.echo(f"recommendation:                {r.recommendation}")
    typer.echo(f"checked_at:                    {r.checked_at.isoformat()}")


@app.command("history")
def cmd_history(
    symbol: str | None = typer.Argument(default=None, help="Тикер монеты (не с --all)"),
    all_entries: bool = typer.Option(False, "--all", help="Последние записи по всем монетам"),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-n",
        help="Число записей (по умолчанию: 10 для SYMBOL, 20 для --all)",
        min=1,
    ),
) -> None:
    """История сохранённых проверок из data/check_history.json."""
    if all_entries and symbol:
        typer.secho("Укажите либо SYMBOL, либо --all.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if not all_entries and not symbol:
        typer.secho("Укажите тикер монеты или --all.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    n = limit if limit is not None else (20 if all_entries else 10)

    if all_entries:
        entries = _history_repo.get_global_last_n(n)
        log.info("history --all limit=%d count=%d", n, len(entries))
    else:
        norm = Coin.normalize_symbol(symbol or "")
        entries = _history_repo.get_last_n(norm, n)
        log.info("history symbol=%s limit=%d count=%d", norm, n, len(entries))

    print_history_entries(entries)


@app.command("backtest")
def cmd_backtest(
    symbol: str = typer.Argument(..., help="Тикер монеты из хранилища"),
    days: int = typer.Option(
        ...,
        "--days",
        "-d",
        help="Глубина окна в календарных днях (число свечей оценивается по таймфрейму монеты)",
    ),
) -> None:
    """Простой backtest: диапазон в начале окна и шаг вперёд по свечам (close), без торговой симуляции."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    if days < 1:
        typer.secho("Параметр --days должен быть не меньше 1.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        r = run_backtest(coin, days, market=_market)
    except ValidationError as e:
        _handle_validation(e)
        return

    log.info("backtest symbol=%s days=%d lifetime_candles=%d", r.symbol, days, r.lifetime_candles)

    bpd = bars_per_day(coin.timeframe)

    def approx_step_days(n: int) -> str:
        if bpd <= 0:
            return ""
        return f" (~{n / bpd:.1f} d)"

    typer.echo("")
    typer.echo(f"Backtest {r.symbol} ({days} days)")
    typer.echo("")
    typer.echo(f"Start price: {r.start_price:g}")
    typer.echo(f"Range: {r.range_low:g} - {r.range_high:g}")
    typer.echo("")
    typer.echo(f"Lifetime: {r.lifetime_days:.1f} days (≈ {r.lifetime_candles} candle steps)")
    hu = "yes" if r.hit_upper else "no"
    hl = "yes" if r.hit_lower else "no"
    step = r.lifetime_candles + 1
    if r.hit_upper:
        typer.echo(f"Hit upper: {hu} (step {step} from range start)")
    else:
        typer.echo(f"Hit upper: {hu}")
    if r.hit_lower:
        typer.echo(f"Hit lower: {hl} (step {step} from range start)")
    else:
        typer.echo(f"Hit lower: {hl}")
    typer.echo("")
    typer.echo(f"Max deviation: {r.max_deviation_pct:.1f}%")
    typer.echo("")
    typer.echo("Status breakdown (evaluator steps):")
    typer.echo(f"  OK: {r.ok_count}{approx_step_days(r.ok_count)}")
    typer.echo(f"  WARNING: {r.warning_count}{approx_step_days(r.warning_count)}")
    typer.echo(f"  STALE: {r.stale_count}{approx_step_days(r.stale_count)}")
    if r.reposition_count:
        typer.echo(f"  REPOSITION: {r.reposition_count}{approx_step_days(r.reposition_count)}")
    typer.echo("")
    typer.echo("Summary:")
    typer.echo(r.result_summary)
    typer.echo("")
    typer.echo(f"Tested at: {r.tested_at.isoformat()}")


@app.command("optimize")
def cmd_optimize(
    symbol: str = typer.Argument(..., help="Тикер монеты из хранилища"),
    days: int = typer.Option(
        ...,
        "--days",
        "-d",
        help="Глубина окна в календарных днях (как у backtest)",
    ),
) -> None:
    """Сравнить conservative / balanced / aggressive на одной истории (простой score)."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    if days < 1:
        typer.secho("Параметр --days должен быть не меньше 1.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        rows = compare_modes(coin, days, market=_market)
    except ValidationError as e:
        _handle_validation(e)
        return

    log.info("optimize symbol=%s days=%d", norm, days)
    print_mode_comparison_table(norm, days, rows)

    best = best_mode_result(rows)
    if best is not None:
        typer.echo("")
        typer.echo(f"Best mode: {best.mode}")
        typer.echo("")


@app.command("suggest")
def cmd_suggest(
    symbol: str = typer.Argument(..., help="Тикер монеты из хранилища"),
    days: int = typer.Option(
        DEFAULT_LOOKBACK_DAYS,
        "--days",
        "-d",
        help="Глубина окна для сравнения режимов (по умолчанию как lookback по плану)",
    ),
) -> None:
    """Подобрать режим по истории и подсказать, как обновить настройки (без автосохранения)."""
    norm = Coin.normalize_symbol(symbol)
    coin = _service.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    if days < 1:
        typer.secho("Параметр --days должен быть не меньше 1.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        rows = compare_modes(coin, days, market=_market)
    except ValidationError as e:
        _handle_validation(e)
        return

    log.info("suggest symbol=%s days=%d", norm, days)
    print_mode_comparison_table(norm, days, rows)

    best = best_mode_result(rows)
    if best is None:
        return

    typer.echo(f"Best mode: {best.mode}")
    typer.echo("")
    typer.echo("Рекомендация (вручную, без автосмены):")
    typer.echo(
        f"  • Установите mode={best.mode!r} для {norm} в data/coins.json "
        f"(или пересоздайте монету: range remove {norm} && range add {norm} --mode {best.mode} …)."
    )
    typer.echo(
        f"  • Текущий mode в хранилище: {coin.mode!r}. После смены выполните: range recalc {norm}"
    )
    typer.echo("")


@app.command("set-active")
def cmd_set_active(
    symbol: str = typer.Argument(..., help="Тикер монеты"),
    low: float = typer.Option(..., "--low", help="Нижняя граница"),
    high: float = typer.Option(..., "--high", help="Верхняя граница"),
    comment: str | None = typer.Option(None, "--comment", help="Необязательный комментарий"),
) -> None:
    """Задать активный диапазон для монеты."""
    try:
        coin = _service.set_active_range(symbol, low, high, comment=comment)
    except ValidationError as e:
        _handle_validation(e)
        return
    log.info(
        "set-active symbol=%s low=%s high=%s",
        coin.symbol,
        coin.active_range.low if coin.active_range else "",
        coin.active_range.high if coin.active_range else "",
    )
    typer.echo(f"Активный диапазон для {coin.symbol} сохранён (set_at={coin.active_range.set_at.isoformat()})")


@app.command("clear-active")
def cmd_clear_active(symbol: str = typer.Argument(..., help="Тикер монеты")) -> None:
    """Сбросить активный диапазон."""
    try:
        coin = _service.clear_active(symbol)
    except ValidationError as e:
        _handle_validation(e)
        return
    log.info("clear-active symbol=%s", coin.symbol)
    typer.echo(f"Активный диапазон для {coin.symbol} удалён (updated_at={coin.updated_at.isoformat()})")


def _run_interactive_menu() -> None:
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
    _run_interactive_menu()


@app.command("ui", help="То же, что menu: интерактивный режим.")
def cmd_ui() -> None:
    _run_interactive_menu()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
