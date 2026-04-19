"""Формирование и вывод отчета для команды `range check --all`.

Модуль отвечает за:
- преобразование `CheckResult` в строки отчета;
- форматирование чисел и процентов для CLI;
- цветной вывод таблицы и агрегированной сводки по статусам;
- экспорт отчёта в TXT/CSV/TSV;
- выбор подмножества строк (фильтры, top-N, “worst” по отклонению).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import typer

from range_program.models.check_result import CheckResult

# Приоритет сортировки для строк отчета:
# чем меньше число, тем выше строка поднимается в итоговой таблице.
STATUS_SORT_ORDER: dict[str, int] = {
    "OUT_OF_RANGE": 0,
    "ERROR": 1,
    "REPOSITION": 2,
    "STALE": 3,
    "WARNING": 4,
    "OK": 5,
}


def status_sort_key(status: str) -> int:
    """Вернуть числовой приоритет статуса для сортировки."""
    return STATUS_SORT_ORDER.get(status, 99)


def _fmt_price(p: float) -> str:
    """Форматировать цену для компактного табличного отображения."""
    if p >= 1000:
        return f"{p:,.0f}".replace(",", "")
    if p >= 1:
        s = f"{p:.2f}"
        return s.rstrip("0").rstrip(".")
    return f"{p:.6g}"


def _fmt_range(lo: float, hi: float) -> str:
    """Собрать строку диапазона `low-high` в человекочитаемом виде."""
    return f"{_fmt_num(lo)}–{_fmt_num(hi)}"


def _fmt_num(n: float) -> str:
    """Показать целые значения без дробной части, остальные как есть."""
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:g}"


def _fmt_pct(x: float) -> str:
    """Форматировать процент с одной цифрой после запятой."""
    return f"{x:.1f}%"


@dataclass(frozen=True)
class CheckTableRow:
    """Нормализованная строка для вывода результата проверки в таблицу."""
    symbol: str
    price: str
    price_value: float | None
    active_range: str
    active_low: float | None
    active_high: float | None
    rec_range: str
    rec_low: float | None
    rec_high: float | None
    dist_down: str
    dist_down_value: float | None
    dist_up: str
    dist_up_value: float | None
    dev: str
    dev_value: float | None
    status: str
    recommendation: str | None = None

    @property
    def sort_rank(self) -> int:
        """Ключ сортировки по важности статуса."""
        return status_sort_key(self.status)

    @classmethod
    def from_check_result(cls, r: CheckResult) -> CheckTableRow:
        """Сконвертировать доменную модель `CheckResult` в строку таблицы."""
        return cls(
            symbol=r.symbol,
            price=_fmt_price(r.current_price),
            price_value=float(r.current_price),
            active_range=_fmt_range(r.active_low, r.active_high),
            active_low=float(r.active_low),
            active_high=float(r.active_high),
            rec_range=_fmt_range(r.recommended_low, r.recommended_high),
            rec_low=float(r.recommended_low),
            rec_high=float(r.recommended_high),
            dist_down=_fmt_pct(r.distance_to_lower_pct),
            dist_down_value=float(r.distance_to_lower_pct),
            dist_up=_fmt_pct(r.distance_to_upper_pct),
            dist_up_value=float(r.distance_to_upper_pct),
            dev=_fmt_pct(r.deviation_from_active_center_pct),
            dev_value=float(r.deviation_from_active_center_pct),
            status=r.status,
            recommendation=r.recommendation,
        )

    @classmethod
    def error_row(cls, symbol: str, message: str) -> CheckTableRow:
        """Построить строку ошибки, обрезав длинное сообщение для колонки DEV."""
        short = message.replace("\n", " ").strip()
        if len(short) > 24:
            short = short[:21] + "..."
        return cls(
            symbol=symbol,
            price="—",
            price_value=None,
            active_range="—",
            active_low=None,
            active_high=None,
            rec_range="—",
            rec_low=None,
            rec_high=None,
            dist_down="—",
            dist_down_value=None,
            dist_up="—",
            dist_up_value=None,
            dev=short if short else "—",
            dev_value=None,
            status="ERROR",
            recommendation=message,
        )


def _status_fg(status: str) -> str:
    """Цвет строки по статусу (Typer/Click)."""
    c = typer.colors
    if status == "ERROR":
        return c.RED
    if status == "OUT_OF_RANGE":
        return c.RED
    if status == "REPOSITION":
        return getattr(c, "MAGENTA", c.YELLOW)
    if status == "STALE":
        return c.YELLOW
    if status == "WARNING":
        return c.WHITE
    if status == "OK":
        return c.GREEN
    return c.WHITE


def _col_widths(rows: list[CheckTableRow], headers: tuple[str, ...]) -> list[int]:
    """Рассчитать ширину каждой колонки по заголовкам и содержимому."""
    w = [len(h) for h in headers]
    for r in rows:
        vals = (r.symbol, r.price, r.active_range, r.rec_range, r.dist_down, r.dist_up, r.dev, r.status)
        for i, v in enumerate(vals):
            w[i] = max(w[i], len(v))
    return w


def format_check_all_table(rows: list[CheckTableRow]) -> str:
    """Сформировать таблицу как текст (для сохранения в файл)."""
    headers = (
        "SYMBOL",
        "PRICE",
        "ACTIVE RANGE",
        "REC RANGE",
        "DIST↓",
        "DIST↑",
        "DEV",
        "STATUS",
    )
    if not rows:
        return "(нет монет для проверки)\n"

    widths = _col_widths(rows, headers)

    def line(parts: tuple[str, ...]) -> str:
        cells = []
        for i, p in enumerate(parts):
            cells.append(p.ljust(widths[i]))
        return "  ".join(cells) + "\n"

    out = ""
    out += line(headers)
    for r in rows:
        out += line((r.symbol, r.price, r.active_range, r.rec_range, r.dist_down, r.dist_up, r.dev, r.status))
    return out


def format_check_all_csv(rows: list[CheckTableRow], *, delimiter: str = ",") -> str:
    """Экспорт отчёта в CSV/TSV (delimiter=',' или '\\t')."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(
        [
            "symbol",
            "status",
            "price",
            "active_low",
            "active_high",
            "rec_low",
            "rec_high",
            "dist_down_pct",
            "dist_up_pct",
            "deviation_pct",
            "recommendation",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r.symbol,
                r.status,
                r.price_value if r.price_value is not None else "",
                r.active_low if r.active_low is not None else "",
                r.active_high if r.active_high is not None else "",
                r.rec_low if r.rec_low is not None else "",
                r.rec_high if r.rec_high is not None else "",
                r.dist_down_value if r.dist_down_value is not None else "",
                r.dist_up_value if r.dist_up_value is not None else "",
                r.dev_value if r.dev_value is not None else "",
                r.recommendation or "",
            ]
        )
    return buf.getvalue()


def format_summary(counts: dict[str, int]) -> str:
    """Сформировать сводку как текст (для сохранения в файл)."""
    out = "\nSummary:\n"
    order = ("OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING", "OK", "ERROR")
    for k in order:
        out += f"  {k}: {counts.get(k, 0)}\n"
    return out


def select_rows(
    rows: list[CheckTableRow],
    *,
    statuses: set[str] | None = None,
    top_n: int | None = None,
    exclude_ok_by_default: bool = False,
) -> list[CheckTableRow]:
    """
    Подготовить строки отчёта: фильтр по статусам и/или top-N “самых проблемных”.

    - statuses=None: оставить все статусы (или исключить OK, если exclude_ok_by_default=True)
    - statuses={...}: оставить только эти статусы
    - top_n: взять первые N строк после сортировки по важности (sort_rank) и symbol
    """
    filtered = list(rows)
    if statuses is not None:
        filtered = [r for r in filtered if r.status in statuses]
    elif exclude_ok_by_default:
        filtered = [r for r in filtered if r.status != "OK"]

    filtered.sort(key=lambda r: (r.sort_rank, r.symbol))
    if top_n is not None and top_n > 0:
        return filtered[: int(top_n)]
    return filtered


def select_worst_rows(
    rows: list[CheckTableRow],
    *,
    statuses: set[str] | None = None,
    top_n: int = 10,
) -> list[CheckTableRow]:
    """
    Top-N “самых проблемных” строк.

    Сортировка:
    1) по важности статуса (OUT_OF_RANGE → ... → OK),
    2) внутри статуса — по deviation_pct по убыванию,
    3) затем по symbol.
    """
    pool = list(rows)
    if statuses is not None:
        pool = [r for r in pool if r.status in statuses]
    pool.sort(
        key=lambda r: (
            r.sort_rank,
            -float(r.dev_value or -1.0),
            r.symbol,
        )
    )
    if top_n <= 0:
        return pool
    return pool[: int(top_n)]


def print_check_all_table(
    rows: list[CheckTableRow],
    *,
    statuses: set[str] | None = None,
    top_n: int | None = None,
    exclude_ok_by_default: bool = False,
) -> None:
    """Вывести цветную таблицу результатов `range check --all` в CLI (с опциональными фильтрами)."""
    headers = (
        "SYMBOL",
        "PRICE",
        "ACTIVE RANGE",
        "REC RANGE",
        "DIST↓",
        "DIST↑",
        "DEV",
        "STATUS",
    )
    rows = select_rows(rows, statuses=statuses, top_n=top_n, exclude_ok_by_default=exclude_ok_by_default)
    if not rows:
        typer.echo("(нет монет для проверки)")
        return

    widths = _col_widths(rows, headers)

    def line(parts: tuple[str, ...], fg: str | None = None) -> None:
        cells = []
        for i, p in enumerate(parts):
            cells.append(p.ljust(widths[i]))
        s = "  ".join(cells)
        if fg:
            typer.secho(s, fg=fg)
        else:
            typer.echo(s)

    line(headers, fg=None)
    for r in rows:
        line(
            (
                r.symbol,
                r.price,
                r.active_range,
                r.rec_range,
                r.dist_down,
                r.dist_up,
                r.dev,
                r.status,
            ),
            fg=_status_fg(r.status),
        )


def print_summary(counts: dict[str, int]) -> None:
    """Вывести сводку количества инструментов по каждому статусу."""
    typer.echo("")
    typer.echo("Summary:")
    order = ("OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING", "OK", "ERROR")
    for k in order:
        typer.echo(f"  {k}: {counts.get(k, 0)}")


def aggregate_counts(rows: list[CheckTableRow]) -> dict[str, int]:
    """Подсчитать распределение статусов по строкам таблицы."""
    keys = ("OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING", "OK", "ERROR")
    out = {k: 0 for k in keys}
    for r in rows:
        st = r.status
        if st == "ERROR":
            out["ERROR"] += 1
        elif st in out:
            out[st] += 1
    return out
