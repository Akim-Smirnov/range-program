"""
Интерактивное терминальное меню Range Program (TUI).

Этот модуль реализует текстовое меню на базе `questionary` и служит “обвязкой”
вокруг доменных сервисов:
- управление монетами (`CoinService`),
- получение рыночных данных (`MarketDataService`),
- пересчёт рекомендаций (`RecalcService`),
- проверки диапазона и история (`CheckService` и `CheckHistoryRepository`),
- бэктест и оптимизация.

Ключевой принцип: в меню нет тяжёлой бизнес-логики. Меню:
- задаёт вопросы пользователю,
- вызывает сервисы,
- показывает результат,
- ловит доменные ошибки и печатает понятные сообщения.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import questionary
import typer
from questionary import Choice

from range_program.check_all_report import (
    aggregate_counts,
    format_check_all_table,
    format_summary,
    print_check_all_table,
    print_summary,
    select_rows,
)
from range_program.config import DEFAULT_QUOTE_ASSET
from range_program.display_helpers import (
    print_grid_setups_block,
    print_mode_comparison_table,
    print_recalc_center_comparison_table,
    print_recalc_width_comparison_table,
)
from range_program.history_view import print_history_entries
from range_program.models.coin import Coin
from range_program.models.defaults import (
    ALLOWED_CENTER_METHODS,
    ALLOWED_MODES,
    ALLOWED_WIDTH_METHODS,
    DEFAULT_CENTER_METHOD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_WIDTH_METHOD,
)
from range_program.repositories.check_history_repository import CheckHistoryRepository
from range_program.services.backtest import run_backtest
from range_program.services.check_service import CheckService
from range_program.services.coin_service import CoinService
from range_program.services.market_data import MarketDataError, MarketDataService
from range_program.services.optimizer import best_mode_result, compare_modes
from range_program.services.range_engine import RangeEngineError, min_candles_required
from range_program.services.recalc_service import (
    RecalcService,
    bars_per_day,
    estimate_candle_limit_with_min,
)
from range_program.validation import ValidationError


NEXT_BACK = "back"
NEXT_MAIN = "main"
NEXT_EXIT = "exit"
_RECALC_SAVE_ACTIVE_COMMENT = "Сохранено из recommended_range после recalc (меню)"


def parse_optional_float(raw: str) -> float | None:
    """Пустая строка → None; иначе float. Для опционального capital и числовых полей."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError as e:
        raise ValueError(
            "Ожидалось число; для пропуска оставьте поле пустым."
        ) from e


def parse_optional_str(raw: str) -> str | None:
    """Пустая строка → None; иначе строка без пробелов по краям."""
    s = (raw or "").strip()
    return s if s else None


def parse_int_with_default(raw: str, *, default: int, minimum: int | None = None) -> int:
    """Парсит int, позволяя пустую строку как значение `default`."""
    s = (raw or "").strip()
    if not s:
        n = default
    else:
        n = int(s, 10)
    if minimum is not None and n < minimum:
        raise ValueError(f"значение должно быть не меньше {minimum}")
    return n


def _echo_error(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED)


def _safe_call(fn: Callable[[], None]) -> None:
    """Запуск действия меню с единообразной обработкой ошибок."""
    try:
        fn()
    except ValidationError as e:
        _echo_error(str(e))
    except MarketDataError as e:
        _echo_error(str(e))
    except RangeEngineError as e:
        _echo_error(str(e))
    except ValueError as e:
        _echo_error(f"Неверный ввод: {e}")


@dataclass(frozen=True)
class MenuDeps:
    coins: CoinService
    market: MarketDataService
    recalc: RecalcService
    check: CheckService
    history_repo: CheckHistoryRepository


def prompt_next_step(section: str) -> Literal["back", "main", "exit"]:
    """После действия: назад в раздел, главное меню или выход."""
    pick = questionary.select(
        "Дальше",
        choices=[
            Choice(title=f"Назад: {section}", value=NEXT_BACK),
            Choice(title="Главное меню", value=NEXT_MAIN),
            Choice(title="Выход", value=NEXT_EXIT),
        ],
        style=questionary.Style([("selected", "fg:cyan bold")]),
    ).ask()
    if pick is None:
        return NEXT_EXIT
    return pick  # type: ignore[return-value]


def _pick_coin_symbol(deps: MenuDeps, *, title: str) -> str | None:
    coins = sorted(deps.coins.list_coins(), key=lambda c: c.symbol)
    if not coins:
        typer.secho("Список монет пуст. Сначала добавьте монету (Coins → Add coin).", fg=typer.colors.YELLOW)
        return None
    choices = [Choice(title=c.symbol, value=c.symbol) for c in coins]
    choices.append(Choice(title="[Отмена]", value=""))
    sym = questionary.select(title, choices=choices, style=questionary.Style([("selected", "fg:cyan bold")])).ask()
    if not sym:
        return None
    return sym


def _print_coin_details(deps: MenuDeps, norm: str) -> None:
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    typer.echo(f"symbol:         {coin.symbol}")
    typer.echo(f"mode:           {coin.mode}")
    typer.echo(f"timeframe:      {coin.timeframe}")
    typer.echo(f"lookback_days:  {coin.lookback_days}")
    typer.echo(f"center_method:  {coin.center_method}")
    typer.echo(f"width_method:   {coin.width_method}")
    typer.echo(f"created_at:     {coin.created_at.isoformat()}")
    typer.echo(f"updated_at:     {coin.updated_at.isoformat()}")
    if coin.capital is None:
        typer.echo("capital:        (none)")
    else:
        typer.echo(f"capital:        {coin.capital} {DEFAULT_QUOTE_ASSET}")
    typer.echo(f"preferred exchange: {coin.exchange or '(none)'}")
    typer.echo(f"preferred quote:    {coin.quote_asset or '(none)'}")
    typer.echo(f"resolved exchange:  {coin.resolved_exchange or '(none)'}")
    typer.echo(f"resolved pair:      {coin.resolved_symbol_pair or '(none)'}")
    if coin.resolved_at is None:
        typer.echo("resolved at:        (none)")
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
                    f"  - {g.mode}: {g.grid_count} grids, {g.step_pct:.2f}%, "
                    f"{g.order_size:.2f} {DEFAULT_QUOTE_ASSET}/order"
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
        quote = deps.market.get_price_quote(norm, coin=coin)
        typer.echo(f"last_price:     {quote.price}")
        typer.echo(f"price_as_of:    {quote.as_of.isoformat()}")
    except MarketDataError as e:
        typer.secho(f"market:         не удалось получить цену ({e})", fg=typer.colors.YELLOW)


def _coins_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Coins",
            choices=[
                Choice("Список монет", value="list"),
                Choice("Детали монеты", value="show"),
                Choice("Добавить монету", value="add"),
                Choice("Удалить монету", value="remove"),
                Choice("Задать capital", value="set_cap"),
                Choice("Сбросить capital", value="clr_cap"),
                Choice("Задать active range", value="set_active"),
                Choice("Сбросить active range", value="clr_active"),
                Choice("Resolve market", value="resolve"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "list":
            _safe_call(lambda: _do_list_coins(deps))
        elif act == "show":
            _safe_call(lambda: _do_show_coin(deps))
        elif act == "add":
            _safe_call(lambda: _do_add_coin(deps))
        elif act == "remove":
            _safe_call(lambda: _do_remove_coin(deps))
        elif act == "set_cap":
            _safe_call(lambda: _do_set_capital(deps))
        elif act == "clr_cap":
            _safe_call(lambda: _do_clear_capital(deps))
        elif act == "set_active":
            _safe_call(lambda: _do_set_active(deps))
        elif act == "clr_active":
            _safe_call(lambda: _do_clear_active(deps))
        elif act == "resolve":
            _safe_call(lambda: _do_resolve_market(deps))

        nxt = prompt_next_step("Coins")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_list_coins(deps: MenuDeps) -> None:
    coins = deps.coins.list_coins()
    if not coins:
        typer.echo("(список пуст)")
        return
    for c in sorted(coins, key=lambda x: x.symbol):
        cap = "—" if c.capital is None else str(c.capital)
        typer.echo(
            f"{c.symbol}\t{c.mode}\t{c.timeframe}\tlookback={c.lookback_days}\tcapital={cap}\t{c.updated_at.isoformat()}"
        )


def _do_show_coin(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    _print_coin_details(deps, Coin.normalize_symbol(sym))


def _do_add_coin(deps: MenuDeps) -> None:
    sym_raw = questionary.text("Symbol (тикер, например BTC)", validate=lambda x: len(x.strip()) > 0).ask()
    if sym_raw is None:
        return
    norm = Coin.normalize_symbol(sym_raw)
    mode = questionary.select(
        "Mode",
        choices=sorted(ALLOWED_MODES),
        default=DEFAULT_MODE,
    ).ask()
    if mode is None:
        return
    tf = questionary.text("Timeframe", default=DEFAULT_TIMEFRAME).ask()
    if tf is None:
        return
    lb_raw = questionary.text(
        "Lookback (дней)",
        default=str(DEFAULT_LOOKBACK_DAYS),
    ).ask()
    if lb_raw is None:
        return
    lookback = parse_int_with_default(lb_raw, default=DEFAULT_LOOKBACK_DAYS, minimum=1)
    cm = questionary.text("Center method", default=DEFAULT_CENTER_METHOD).ask()
    if cm is None:
        return
    wm = questionary.text("Width method", default=DEFAULT_WIDTH_METHOD).ask()
    if wm is None:
        return
    cap_raw = questionary.text(
        f"Capital ({DEFAULT_QUOTE_ASSET}, опционально; Enter = пропустить)",
        default="",
    ).ask()
    if cap_raw is None:
        return
    capital = parse_optional_float(cap_raw)
    ex_raw = questionary.text("Preferred exchange (опционально; Enter = пропустить)", default="").ask()
    if ex_raw is None:
        return
    q_raw = questionary.text("Preferred quote asset (опционально; Enter = пропустить)", default="").ask()
    if q_raw is None:
        return
    ok, coin = deps.coins.add_coin(
        norm,
        mode=mode,
        timeframe=tf.strip(),
        lookback_days=lookback,
        center_method=cm.strip(),
        width_method=wm.strip(),
        capital=capital,
        exchange=parse_optional_str(ex_raw),
        quote_asset=parse_optional_str(q_raw),
    )
    if not ok:
        typer.secho(f"Монета {norm} уже есть.", fg=typer.colors.YELLOW)
        return
    assert coin is not None
    typer.echo(f"Добавлено: {coin.symbol} (создана {coin.created_at.isoformat()})")


def _do_remove_coin(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Удалить монету")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    ok = questionary.confirm(f"Удалить {norm} из хранилища?", default=False).ask()
    if not ok:
        typer.echo("Отменено.")
        return
    if not deps.coins.remove_coin(norm):
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    typer.echo(f"Удалено: {norm}")


def _do_set_capital(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    amt_raw = questionary.text(f"Сумма ({DEFAULT_QUOTE_ASSET})").ask()
    if amt_raw is None:
        return
    amount = float((amt_raw or "").strip())
    coin = deps.coins.set_capital(sym, amount)
    typer.echo(f"capital для {coin.symbol} установлен: {amount} {DEFAULT_QUOTE_ASSET}")


def _do_clear_capital(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    if not questionary.confirm("Сбросить capital для этой монеты?", default=False).ask():
        typer.echo("Отменено.")
        return
    coin = deps.coins.clear_capital(sym)
    typer.echo(f"capital для {coin.symbol} сброшен.")


def _do_set_active(deps: MenuDeps) -> None:
    """Задать active_range (как стоит бот) вручную."""
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin_before = deps.coins.get_coin(norm)
    if coin_before is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return

    if coin_before.active_range is not None:
        ar = coin_before.active_range
        typer.echo("Текущий active_range:")
        typer.echo(f"  low={ar.low:g} high={ar.high:g} set_at={ar.set_at.isoformat()} comment={ar.comment!r}")
        typer.echo("")

    default_low = str(coin_before.active_range.low) if coin_before.active_range is not None else ""
    default_high = str(coin_before.active_range.high) if coin_before.active_range is not None else ""
    low_s = questionary.text("Нижняя граница (low)", default=default_low).ask()
    high_s = questionary.text("Верхняя граница (high)", default=default_high).ask()
    if low_s is None or high_s is None:
        return
    low = float(low_s.strip())
    high = float(high_s.strip())
    cmt = questionary.text("Комментарий (опционально; Enter = нет)", default="").ask()
    if cmt is None:
        return
    comment = parse_optional_str(cmt)
    coin = deps.coins.set_active_range(sym, low, high, comment=comment)
    ar = coin.active_range
    assert ar is not None
    typer.echo(f"Активный диапазон для {coin.symbol} сохранён (set_at={ar.set_at.isoformat()})")

    # Быстрая проверка: насколько active_range отличается от recommended_range (если он есть).
    if coin.recommended_range is not None:
        rr = coin.recommended_range
        active_center = (ar.low + ar.high) / 2.0
        rec_center = float(rr.center)
        if rec_center > 0 and active_center > 0:
            center_diff_pct = abs(active_center - rec_center) / rec_center * 100.0
            active_width_pct = ((ar.high - ar.low) / active_center) * 100.0
            width_diff_pct = abs(active_width_pct - float(rr.width_pct))
            if center_diff_pct > 10.0 or width_diff_pct > 15.0:
                typer.echo("")
                typer.secho(
                    "Внимание: active_range заметно отличается от recommended_range.",
                    fg=typer.colors.YELLOW,
                )
                typer.echo(f"  center diff ≈ {center_diff_pct:g}%")
                typer.echo(f"  width diff  ≈ {width_diff_pct:g} п.п.")


def _do_clear_active(deps: MenuDeps) -> None:
    """Сбросить active_range (как стоит бот)."""
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    if not questionary.confirm("Сбросить активный диапазон?", default=False).ask():
        typer.echo("Отменено.")
        return
    cmt = questionary.text("Комментарий (опционально; Enter = нет)", default="").ask()
    if cmt is None:
        return
    comment = parse_optional_str(cmt)
    coin = deps.coins.clear_active_range(sym, comment=comment)
    typer.echo(f"Активный диапазон для {coin.symbol} удалён (updated_at={coin.updated_at.isoformat()})")


def _do_resolve_market(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    m = deps.market.resolve_market(coin)
    now = datetime.now(timezone.utc)
    updated = replace(
        coin,
        resolved_exchange=m.exchange,
        resolved_symbol_pair=m.symbol_pair,
        resolved_at=now,
        updated_at=now,
    )
    if not deps.coins.update_coin(updated):
        _echo_error("Не удалось сохранить монету.")
        return
    typer.echo("")
    typer.echo(f"Symbol: {norm}")
    typer.echo(f"Resolved exchange: {m.exchange}")
    typer.echo(f"Resolved pair: {m.symbol_pair}")
    typer.echo(f"Quote asset: {m.quote_asset}")


def _market_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Market data",
            choices=[
                Choice("Текущая цена", value="price"),
                Choice("Свечи (OHLCV)", value="candles"),
                Choice("Resolve market", value="resolve"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "price":
            _safe_call(lambda: _do_price(deps))
        elif act == "candles":
            _safe_call(lambda: _do_candles(deps))
        elif act == "resolve":
            _safe_call(lambda: _do_resolve_market(deps))

        nxt = prompt_next_step("Market data")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_price(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    q = deps.market.get_price_quote(norm, coin=coin)
    pair = deps.market.pair_for_symbol(norm, coin=coin)
    typer.echo(f"{norm}\t{pair}\t{q.price}\t{q.as_of.isoformat()}")


def _do_candles(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        return
    lim_raw = questionary.text("Сколько последних свечей?", default="10").ask()
    if lim_raw is None:
        return
    limit = parse_int_with_default(lim_raw, default=10, minimum=1)
    candles = deps.market.get_ohlcv(norm, coin.timeframe, limit, coin=coin)
    typer.echo(f"pair={deps.market.pair_for_symbol(norm, coin=coin)} timeframe={coin.timeframe} limit={len(candles)}")
    typer.echo("time(UTC)\topen\thigh\tlow\tclose\tvolume")
    for bar in candles:
        typer.echo(
            f"{bar.timestamp.isoformat()}\t{bar.open}\t{bar.high}\t{bar.low}\t{bar.close}\t{bar.volume}"
        )


def _range_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Range analysis",
            choices=[
                Choice("Пересчитать диапазон (recalc)", value="recalc"),
                Choice("Recalc с параметрами (анализ/override)", value="recalc_params"),
                Choice("Показать recommended range", value="show_rr"),
                Choice("Показать grid setups", value="grids"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "recalc":
            _safe_call(lambda: _do_recalc(deps))
        elif act == "recalc_params":
            _safe_call(lambda: _do_recalc_with_params(deps))
        elif act == "show_rr":
            _safe_call(lambda: _do_show_recommended(deps))
        elif act == "grids":
            _safe_call(lambda: _do_show_grids(deps))

        nxt = prompt_next_step("Range analysis")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_recalc(deps: MenuDeps) -> None:
    """Recalc по сохранённым настройкам монеты (с сохранением результата)."""
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin_before = deps.coins.get_coin(norm)
    out = deps.recalc.recalc(sym)
    rr = out.recommended
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
            "Capital не задан; сетки недоступны. Задайте capital в разделе Coins.",
            fg=typer.colors.YELLOW,
        )

    _offer_save_recommended_as_active(deps, norm)


def _do_recalc_with_params(deps: MenuDeps) -> None:
    """
    Recalc с параметрами (override) для анализа без записи.

    Сценарий:
    1) спрашиваем параметры (timeframe/lookback/методы),
    2) показываем диагностическую информацию (need/limit/биржа/пара),
    3) выполняем recalc с save=False,
    4) предлагаем (по желанию) пересчитать ещё раз с save=True, чтобы сохранить.
    """
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        return

    # Вопросы к пользователю. Дефолты = текущие значения монеты.
    tf_raw = questionary.text(
        "timeframe (например 4h, 1d)",
        default=str(coin.timeframe),
    ).ask()
    if tf_raw is None:
        return
    timeframe = str(tf_raw).strip() or str(coin.timeframe)

    lb_raw = questionary.text(
        "lookback_days (глубина истории в днях)",
        default=str(coin.lookback_days),
    ).ask()
    if lb_raw is None:
        return
    lookback_days = int(str(lb_raw).strip() or coin.lookback_days)

    center_choices = [coin.center_method] + [m for m in sorted(ALLOWED_CENTER_METHODS) if m != coin.center_method]
    cm = questionary.select(
        "center_method",
        choices=[Choice(m, value=m) for m in center_choices],
        style=questionary.Style([("selected", "fg:cyan bold")]),
    ).ask()
    if cm is None:
        return
    center_method = str(cm)

    width_choices = [coin.width_method] + [w for w in sorted(ALLOWED_WIDTH_METHODS) if w != coin.width_method]
    wm = questionary.select(
        "width_method",
        choices=[Choice(w, value=w) for w in width_choices],
        style=questionary.Style([("selected", "fg:cyan bold")]),
    ).ask()
    if wm is None:
        return
    width_method = str(wm)

    working = coin.with_settings(
        timeframe=timeframe,
        lookback_days=lookback_days,
        center_method=center_method,
        width_method=width_method,
    )

    need = min_candles_required(working.center_method, working.width_method)
    limit = estimate_candle_limit_with_min(working.timeframe, working.lookback_days, min_required=need)

    typer.echo("")
    typer.echo("Диагностика перед recalc:")
    typer.echo(f"  settings: timeframe={working.timeframe} lookback_days={working.lookback_days}")
    typer.echo(f"           center_method={working.center_method} width_method={working.width_method}")
    typer.echo(f"  candles: need(min)={need} limit(request)={limit} bars/day≈{bars_per_day(working.timeframe):g}")

    try:
        match = deps.market.resolve_market(coin)
        typer.echo(f"  market:  {match.exchange}:{match.symbol_pair}")
    except MarketDataError as e:
        typer.secho(f"  market:  не удалось определить заранее: {e}", fg=typer.colors.YELLOW)

    typer.echo("")
    typer.secho("Запуск recalc в режиме анализа (без сохранения)...", fg=typer.colors.CYAN)
    out = deps.recalc.recalc(
        sym,
        timeframe=working.timeframe,
        lookback_days=working.lookback_days,
        center_method=working.center_method,
        width_method=working.width_method,
        save=False,
    )
    rr = out.recommended
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

    if questionary.confirm(
        "Сохранить рассчитанный recommended_range и параметры в монету?",
        default=False,
    ).ask():
        typer.echo("")
        typer.secho("Сохраняю (выполняю recalc ещё раз с save=True)...", fg=typer.colors.CYAN)
        deps.recalc.recalc(
            sym,
            timeframe=working.timeframe,
            lookback_days=working.lookback_days,
            center_method=working.center_method,
            width_method=working.width_method,
            save=True,
        )
        _offer_save_recommended_as_active(deps, norm)


def _offer_save_recommended_as_active(deps: MenuDeps, symbol: str) -> None:
    if not questionary.confirm(
        "Сохранить рассчитанный recommended_range как active range?",
        default=False,
    ).ask():
        return

    norm = Coin.normalize_symbol(symbol)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    rr = coin.recommended_range
    if rr is None:
        typer.secho(
            "Не удалось сохранить active range: у монеты нет recommended_range после recalc.",
            fg=typer.colors.YELLOW,
        )
        return

    cmt = questionary.text(
        "Комментарий к active_range (опционально)",
        default=_RECALC_SAVE_ACTIVE_COMMENT,
    ).ask()
    if cmt is None:
        return
    comment = parse_optional_str(cmt) or _RECALC_SAVE_ACTIVE_COMMENT

    updated = deps.coins.set_active_range(
        norm,
        rr.low,
        rr.high,
        comment=comment,
    )
    ar = updated.active_range
    if ar is None:
        typer.secho("Не удалось сохранить active range.", fg=typer.colors.RED)
        return
    typer.echo(f"Активный диапазон для {updated.symbol} сохранён (set_at={ar.set_at.isoformat()})")


def _do_show_recommended(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    if coin.recommended_range is None:
        typer.secho("Нет recommended_range. Выполните recalc.", fg=typer.colors.YELLOW)
        return
    rr = coin.recommended_range
    typer.echo("recommended_range:")
    typer.echo(f"  low:           {rr.low}")
    typer.echo(f"  high:          {rr.high}")
    typer.echo(f"  center:        {rr.center}")
    typer.echo(f"  width_pct:     {rr.width_pct}")
    typer.echo(f"  calculated_at: {rr.calculated_at.isoformat()}")
    typer.echo(f"  center_method: {rr.center_method}")
    typer.echo(f"  width_method:  {rr.width_method}")


def _do_show_grids(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    if coin.recommended_range is None:
        typer.secho("Нет recommended_range. Сначала recalc.", fg=typer.colors.YELLOW)
        return
    rr = coin.recommended_range
    if coin.capital is None:
        typer.secho(
            "Capital не задан; варианты сетки не считаются. Задайте capital в разделе Coins.",
            fg=typer.colors.YELLOW,
        )
        return
    if not rr.grid_configs:
        typer.secho("В recommended_range нет grid_configs.", fg=typer.colors.YELLOW)
        return
    print_grid_setups_block(rr.grid_configs, quote=DEFAULT_QUOTE_ASSET)


def _checks_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Checks",
            choices=[
                Choice("Проверить одну монету", value="one"),
                Choice("Проверить все монеты", value="all"),
                Choice("Проверить все (только проблемные)", value="all_problems"),
                Choice("Проверить все и сохранить отчёт", value="all_save"),
                Choice("Последняя проверка по монете", value="last"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "one":
            _safe_call(lambda: _do_check_one(deps))
        elif act == "all":
            _safe_call(lambda: _do_check_all(deps))
        elif act == "all_problems":
            _safe_call(lambda: _do_check_all_problems(deps))
        elif act == "all_save":
            _safe_call(lambda: _do_check_all_save(deps))
        elif act == "last":
            _safe_call(lambda: _do_last_check(deps))

        nxt = prompt_next_step("Checks")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_check_one(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    if coin.active_range is None:
        typer.secho(
            f"У монеты {norm} нет active_range. Задайте в разделе Coins → «Задать active range».",
            fg=typer.colors.YELLOW,
        )
        return
    auto = questionary.confirm(
        "Делать автоматический recalc при необходимости?",
        default=True,
    ).ask()
    if auto is None:
        return
    persist = questionary.confirm(
        "Сохранять результат (last_check/история)?",
        default=True,
    ).ask()
    if persist is None:
        return
    r = deps.check.run_check(sym, auto_recalc=bool(auto), persist=bool(persist))
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


def _do_check_all(deps: MenuDeps) -> None:
    auto = questionary.confirm(
        "Делать автоматический recalc при необходимости?",
        default=True,
    ).ask()
    if auto is None:
        return
    persist = questionary.confirm(
        "Сохранять результат (last_check/история)?",
        default=True,
    ).ask()
    if persist is None:
        return
    rows = deps.check.run_check_all(auto_recalc=bool(auto), persist=bool(persist))

    filt = questionary.select(
        "Фильтр для отчёта",
        choices=[
            Choice("Все монеты", value="all"),
            Choice("Только проблемные (без OK)", value="problems"),
            Choice("Только OUT_OF_RANGE и ERROR", value="critical"),
            Choice("Проблемные без ERROR (OUT/REPOSITION/STALE/WARNING)", value="warn"),
        ],
        style=questionary.Style([("selected", "fg:cyan bold")]),
    ).ask()
    if filt is None:
        return

    statuses: set[str] | None = None
    exclude_ok = False
    if filt == "problems":
        exclude_ok = True
    elif filt == "critical":
        statuses = {"OUT_OF_RANGE", "ERROR"}
    elif filt == "warn":
        statuses = {"OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING"}

    top_raw = questionary.text("Top-N строк (0 = все)", default="0").ask()
    if top_raw is None:
        return
    top_n = int(str(top_raw).strip() or "0")
    top_n_opt = None if top_n <= 0 else top_n

    selected = select_rows(rows, statuses=statuses, top_n=top_n_opt, exclude_ok_by_default=exclude_ok)
    print_check_all_table(selected)
    print_summary(aggregate_counts(selected))

    if questionary.confirm("Сохранить этот отчёт в файл?", default=False).ask():
        default_dir = Path(__file__).resolve().parents[2] / "data" / "reports"
        default_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_path = default_dir / f"check_all_{stamp}.txt"
        path_raw = questionary.text("Путь к файлу отчёта", default=str(default_path)).ask()
        if path_raw is None:
            return
        out_path = Path(str(path_raw).strip() or str(default_path))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        txt = format_check_all_table(selected) + format_summary(aggregate_counts(selected))
        out_path.write_text(txt, encoding="utf-8")
        typer.echo(f"Отчёт сохранён: {out_path}")


def _do_check_all_problems(deps: MenuDeps) -> None:
    """Быстрый check all: сразу показать только проблемные строки (без OK)."""
    auto = questionary.confirm(
        "Делать автоматический recalc при необходимости?",
        default=True,
    ).ask()
    if auto is None:
        return
    persist = questionary.confirm(
        "Сохранять результат (last_check/история)?",
        default=True,
    ).ask()
    if persist is None:
        return
    rows = deps.check.run_check_all(auto_recalc=bool(auto), persist=bool(persist))
    selected = select_rows(rows, exclude_ok_by_default=True)
    print_check_all_table(selected)
    print_summary(aggregate_counts(selected))


def _do_check_all_save(deps: MenuDeps) -> None:
    """Быстрый check all: сформировать отчёт и сразу сохранить в файл."""
    auto = questionary.confirm(
        "Делать автоматический recalc при необходимости?",
        default=True,
    ).ask()
    if auto is None:
        return
    rows = deps.check.run_check_all(auto_recalc=bool(auto), persist=True)

    # По умолчанию сохраняем только проблемные строки, чтобы файл был компактнее.
    selected = select_rows(rows, exclude_ok_by_default=True)
    print_check_all_table(selected)
    print_summary(aggregate_counts(selected))

    default_dir = Path(__file__).resolve().parents[2] / "data" / "reports"
    default_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_path = default_dir / f"check_all_{stamp}.txt"
    path_raw = questionary.text("Путь к файлу отчёта", default=str(default_path)).ask()
    if path_raw is None:
        return
    out_path = Path(str(path_raw).strip() or str(default_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    txt = format_check_all_table(selected) + format_summary(aggregate_counts(selected))
    out_path.write_text(txt, encoding="utf-8")
    typer.echo(f"Отчёт сохранён: {out_path}")


def _do_last_check(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена.", fg=typer.colors.YELLOW)
        return
    if coin.last_check is None:
        typer.secho("Нет сохранённой последней проверки.", fg=typer.colors.YELLOW)
        return
    lc = coin.last_check
    typer.echo(f"symbol:                        {lc.symbol}")
    typer.echo(f"current_price:                 {lc.current_price}")
    typer.echo(f"active_low:                    {lc.active_low}")
    typer.echo(f"active_high:                   {lc.active_high}")
    typer.echo(f"active_center:                 {lc.active_center}")
    typer.echo(f"recommended_low:               {lc.recommended_low}")
    typer.echo(f"recommended_high:              {lc.recommended_high}")
    typer.echo(f"recommended_center:            {lc.recommended_center}")
    typer.echo(f"distance_to_lower_pct:         {lc.distance_to_lower_pct}")
    typer.echo(f"distance_to_upper_pct:         {lc.distance_to_upper_pct}")
    typer.echo(f"deviation_from_active_center_pct: {lc.deviation_from_active_center_pct}")
    typer.echo(f"status:                        {lc.status}")
    typer.echo(f"recommendation:                {lc.recommendation}")
    typer.echo(f"checked_at:                    {lc.checked_at.isoformat()}")


def _history_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "History",
            choices=[
                Choice("История по монете", value="coin"),
                Choice("Глобальная история", value="global"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "coin":
            _safe_call(lambda: _do_history_coin(deps))
        elif act == "global":
            _safe_call(lambda: _do_history_global(deps))

        nxt = prompt_next_step("History")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_history_coin(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    lim_raw = questionary.text("Сколько записей?", default="10").ask()
    if lim_raw is None:
        return
    n = parse_int_with_default(lim_raw, default=10, minimum=1)
    entries = deps.history_repo.get_last_n(norm, n)
    print_history_entries(entries)


def _do_history_global(deps: MenuDeps) -> None:
    lim_raw = questionary.text("Сколько записей?", default="20").ask()
    if lim_raw is None:
        return
    n = parse_int_with_default(lim_raw, default=20, minimum=1)
    entries = deps.history_repo.get_global_last_n(n)
    print_history_entries(entries)


def _backtest_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Backtest",
            choices=[
                Choice("Запустить backtest", value="run"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "run":
            _safe_call(lambda: _do_backtest(deps))

        nxt = prompt_next_step("Backtest")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_backtest(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        return
    days_raw = questionary.text("Окно (дней)", default=str(DEFAULT_LOOKBACK_DAYS)).ask()
    if days_raw is None:
        return
    days = parse_int_with_default(days_raw, default=DEFAULT_LOOKBACK_DAYS, minimum=1)
    r = run_backtest(coin, days, market=deps.market)
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


def _optimize_section(deps: MenuDeps) -> Literal["main", "exit"]:
    while True:
        act = questionary.select(
            "Optimize",
            choices=[
                Choice("Сравнить режимы (optimize)", value="opt"),
                Choice("Подсказать лучший режим (suggest)", value="sug"),
                Choice("« Назад в главное меню", value="back"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()
        if act is None or act == "back":
            return "main"

        if act == "opt":
            _safe_call(lambda: _do_optimize(deps))
        elif act == "sug":
            _safe_call(lambda: _do_suggest(deps))

        nxt = prompt_next_step("Optimize")
        if nxt == NEXT_EXIT:
            return "exit"
        if nxt == NEXT_MAIN:
            return "main"


def _do_optimize(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        return
    days_raw = questionary.text("Окно (дней)", default=str(DEFAULT_LOOKBACK_DAYS)).ask()
    if days_raw is None:
        return
    days = parse_int_with_default(days_raw, default=DEFAULT_LOOKBACK_DAYS, minimum=1)
    rows = compare_modes(coin, days, market=deps.market)
    print_mode_comparison_table(norm, days, rows)
    best = best_mode_result(rows)
    if best is not None:
        typer.echo("")
        typer.echo(f"Best mode: {best.mode}")
        typer.echo("")


def _do_suggest(deps: MenuDeps) -> None:
    sym = _pick_coin_symbol(deps, title="Монета")
    if sym is None:
        return
    norm = Coin.normalize_symbol(sym)
    coin = deps.coins.get_coin(norm)
    if coin is None:
        typer.secho(f"Монета {norm} не найдена в хранилище.", fg=typer.colors.YELLOW)
        return
    days_raw = questionary.text("Окно (дней)", default=str(DEFAULT_LOOKBACK_DAYS)).ask()
    if days_raw is None:
        return
    days = parse_int_with_default(days_raw, default=DEFAULT_LOOKBACK_DAYS, minimum=1)
    rows = compare_modes(coin, days, market=deps.market)
    print_mode_comparison_table(norm, days, rows)
    best = best_mode_result(rows)
    if best is None:
        return
    typer.echo(f"Best mode: {best.mode}")
    typer.echo("")
    typer.echo("Рекомендация (вручную, без автосмены):")
    typer.echo(
        f"  • Установите mode={best.mode!r} для {norm} в data/coins.json "
        f"(или пересоздайте монету в разделе Coins → «Удалить монету» / «Добавить монету» с нужным mode)."
    )
    typer.echo(
        f"  • Текущий mode в хранилище: {coin.mode!r}. После смены выполните пересчёт: Range analysis → «Пересчитать диапазон»."
    )
    typer.echo("")


def run_interactive_menu(deps: MenuDeps) -> None:
    """Главный цикл интерактивного меню."""
    typer.echo("")
    typer.echo("Range Program — интерактивный режим")
    typer.echo("")

    while True:
        choice = questionary.select(
            "Главное меню",
            choices=[
                Choice("Coins", value="coins"),
                Choice("Market data", value="market"),
                Choice("Range analysis", value="range"),
                Choice("Checks", value="checks"),
                Choice("History", value="history"),
                Choice("Backtest", value="backtest"),
                Choice("Optimize", value="optimize"),
                Choice("Выход", value="exit"),
            ],
            style=questionary.Style([("selected", "fg:cyan bold")]),
        ).ask()

        if choice is None or choice == "exit":
            typer.echo("Выход.")
            return

        sub: Literal["main", "exit"] = "main"
        if choice == "coins":
            sub = _coins_section(deps)
        elif choice == "market":
            sub = _market_section(deps)
        elif choice == "range":
            sub = _range_section(deps)
        elif choice == "checks":
            sub = _checks_section(deps)
        elif choice == "history":
            sub = _history_section(deps)
        elif choice == "backtest":
            sub = _backtest_section(deps)
        elif choice == "optimize":
            sub = _optimize_section(deps)

        if sub == "exit":
            typer.echo("Выход.")
            return
