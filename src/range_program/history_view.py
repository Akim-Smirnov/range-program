"""Вывод истории проверок в терминал (этап 8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import typer


def _fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:19]


def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_price(x: Any) -> str:
    try:
        p = float(x)
        if p >= 1000:
            return f"{p:,.0f}".replace(",", "")
        return f"{p:g}"
    except (TypeError, ValueError):
        return "—"


def print_history_entries(entries: list[dict[str, Any]]) -> None:
    if not entries:
        typer.echo("(нет записей в истории)")
        return
    headers = ("DATE", "PRICE", "STATUS", "DEV", "DIST↓", "DIST↑")
    data_rows: list[tuple[str, ...]] = []
    for e in entries:
        data_rows.append(
            (
                _fmt_dt(str(e.get("checked_at", ""))),
                _fmt_price(e.get("current_price")),
                str(e.get("status", "—")),
                _fmt_pct(e.get("deviation_from_center_pct")),
                _fmt_pct(e.get("distance_to_lower_pct")),
                _fmt_pct(e.get("distance_to_upper_pct")),
            )
        )
    widths = [len(h) for h in headers]
    for row in data_rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(c))

    def line(parts: tuple[str, ...]) -> None:
        typer.echo("  ".join(parts[i].ljust(widths[i]) for i in range(len(parts))))

    line(tuple(headers))
    for row in data_rows:
        line(row)
