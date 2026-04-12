"""Общие блоки текстового вывода для CLI и интерактивного меню."""

from __future__ import annotations

import typer

from range_program.config import DEFAULT_QUOTE_ASSET
from range_program.models.grid_config import GridConfig
from range_program.models.mode_result import ModeResult
from range_program.models.recommended_range import RecommendedRange


def print_grid_setups_block(grid_configs: tuple[GridConfig, ...], *, quote: str = DEFAULT_QUOTE_ASSET) -> None:
    labels = (
        ("aggressive", "Aggressive"),
        ("balanced", "Balanced"),
        ("conservative", "Conservative"),
    )
    typer.echo("")
    typer.echo("Grid setups:")
    by_mode = {g.mode: g for g in grid_configs}
    for key, title in labels:
        g = by_mode.get(key)
        if g is None:
            continue
        typer.echo(f"{title}:")
        typer.echo(f"  grids: {g.grid_count}")
        typer.echo(f"  step: {g.step_pct:.2f}%")
        typer.echo(f"  order size: {g.order_size:.2f} {quote}")


def print_mode_comparison_table(symbol: str, days: int, rows: list[ModeResult]) -> None:
    typer.echo("")
    typer.echo(f"Mode comparison {symbol} ({days} days)")
    typer.echo("")
    headers = ("MODE", "LIFETIME", "OK", "WARNING", "STALE", "DEV%", "SCORE")
    data_rows: list[tuple[str, ...]] = []
    for r in rows:
        data_rows.append(
            (
                r.mode,
                f"{r.lifetime_days:.1f}",
                f"{r.ok_days:.1f}",
                f"{r.warning_days:.1f}",
                f"{r.stale_days:.1f}",
                f"{r.max_deviation_pct:.1f}%",
                f"{r.score:.1f}",
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


def print_recalc_center_comparison_table(
    rows: tuple[tuple[str, RecommendedRange], ...] | list[tuple[str, RecommendedRange]],
    *,
    saved_center_method: str,
) -> None:
    """Таблица сравнения методов центра после recalc; * — строка, сохранённая в монету."""
    if not rows:
        return
    saved = saved_center_method.strip().lower()
    typer.echo("")
    typer.echo("Сравнение center_method (одинаковые mode и ATR; * — сохранённый метод монеты):")
    headers = ("METHOD", "CENTER", "LOW", "HIGH", "WIDTH%")
    data_rows: list[tuple[str, ...]] = []
    for method, rr in rows:
        mark = "*" if method == saved else ""
        label = f"{method}{mark}"
        data_rows.append(
            (
                label,
                f"{rr.center:g}",
                f"{rr.low:g}",
                f"{rr.high:g}",
                f"{rr.width_pct:g}",
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
