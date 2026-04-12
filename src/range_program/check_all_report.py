"""Табличный вывод для `range check --all` (этап 7)."""

from __future__ import annotations

from dataclasses import dataclass

import typer

from range_program.models.check_result import CheckResult

# Приоритет сортировки: проблемные сверху (меньше = важнее)
STATUS_SORT_ORDER: dict[str, int] = {
    "OUT_OF_RANGE": 0,
    "ERROR": 1,
    "REPOSITION": 2,
    "STALE": 3,
    "WARNING": 4,
    "OK": 5,
}


def status_sort_key(status: str) -> int:
    return STATUS_SORT_ORDER.get(status, 99)


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}".replace(",", "")
    if p >= 1:
        s = f"{p:.2f}"
        return s.rstrip("0").rstrip(".")
    return f"{p:.6g}"


def _fmt_range(lo: float, hi: float) -> str:
    return f"{_fmt_num(lo)}–{_fmt_num(hi)}"


def _fmt_num(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:g}"


def _fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


@dataclass(frozen=True)
class CheckTableRow:
    symbol: str
    price: str
    active_range: str
    rec_range: str
    dist_down: str
    dist_up: str
    dev: str
    status: str

    @property
    def sort_rank(self) -> int:
        return status_sort_key(self.status)

    @classmethod
    def from_check_result(cls, r: CheckResult) -> CheckTableRow:
        return cls(
            symbol=r.symbol,
            price=_fmt_price(r.current_price),
            active_range=_fmt_range(r.active_low, r.active_high),
            rec_range=_fmt_range(r.recommended_low, r.recommended_high),
            dist_down=_fmt_pct(r.distance_to_lower_pct),
            dist_up=_fmt_pct(r.distance_to_upper_pct),
            dev=_fmt_pct(r.deviation_from_active_center_pct),
            status=r.status,
        )

    @classmethod
    def error_row(cls, symbol: str, message: str) -> CheckTableRow:
        short = message.replace("\n", " ").strip()
        if len(short) > 24:
            short = short[:21] + "..."
        return cls(
            symbol=symbol,
            price="—",
            active_range="—",
            rec_range="—",
            dist_down="—",
            dist_up="—",
            dev=short if short else "—",
            status="ERROR",
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
    w = [len(h) for h in headers]
    for r in rows:
        vals = (r.symbol, r.price, r.active_range, r.rec_range, r.dist_down, r.dist_up, r.dev, r.status)
        for i, v in enumerate(vals):
            w[i] = max(w[i], len(v))
    return w


def print_check_all_table(rows: list[CheckTableRow]) -> None:
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
    typer.echo("")
    typer.echo("Summary:")
    order = ("OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING", "OK", "ERROR")
    for k in order:
        typer.echo(f"  {k}: {counts.get(k, 0)}")


def aggregate_counts(rows: list[CheckTableRow]) -> dict[str, int]:
    keys = ("OUT_OF_RANGE", "REPOSITION", "STALE", "WARNING", "OK", "ERROR")
    out = {k: 0 for k in keys}
    for r in rows:
        st = r.status
        if st == "ERROR":
            out["ERROR"] += 1
        elif st in out:
            out[st] += 1
    return out
