from __future__ import annotations

from dataclasses import replace

from range_program.models.coin import Coin
from range_program.models.mode_result import ModeResult
from range_program.services.backtest import run_backtest
from range_program.services.evaluator import Evaluator
from range_program.services.market_data import MarketDataService
from range_program.services.range_engine import RangeEngine
from range_program.services.recalc_service import bars_per_day
from range_program.validation import ValidationError

MODES_COMPARISON_ORDER = ("conservative", "balanced", "aggressive")


def _steps_to_days(count: int, bpd: float) -> float:
    if bpd <= 0:
        return 0.0
    return count / bpd


def compute_mode_score(
    lifetime_days: float,
    ok_days: float,
    stale_days: float,
    max_deviation_pct: float,
) -> float:
    """
    Простой скоринг (этап 10):
    дольше жизнь и больше OK — лучше; STALE и большой deviation — хуже.
    """
    return (
        float(lifetime_days)
        + float(ok_days) * 0.5
        - float(stale_days) * 0.7
        - (float(max_deviation_pct) * 0.2)
    )


def compare_modes(
    coin: Coin,
    days: int,
    *,
    market: MarketDataService,
    engine: RangeEngine | None = None,
    evaluator: Evaluator | None = None,
) -> list[ModeResult]:
    """
    Один период истории, три режима — для каждого отдельный run_backtest на копии монеты с другим mode.
    """
    bpd = bars_per_day(coin.timeframe)
    if bpd <= 0:
        raise ValidationError("Не удалось оценить число свечей в день для таймфрейма монеты.")

    out: list[ModeResult] = []
    eng = engine
    ev = evaluator

    for mode in MODES_COMPARISON_ORDER:
        c = replace(coin, mode=mode)
        br = run_backtest(c, days, market=market, engine=eng, evaluator=ev)

        ok_days = _steps_to_days(br.ok_count, bpd)
        warning_days = _steps_to_days(br.warning_count, bpd)
        stale_days = _steps_to_days(br.stale_count, bpd)

        score = compute_mode_score(
            br.lifetime_days,
            ok_days,
            stale_days,
            br.max_deviation_pct,
        )

        summary = _build_mode_summary(
            mode=mode,
            lifetime_days=br.lifetime_days,
            hit_upper=br.hit_upper,
            hit_lower=br.hit_lower,
            score=score,
        )

        out.append(
            ModeResult(
                mode=mode,
                lifetime_days=br.lifetime_days,
                hit_upper=br.hit_upper,
                hit_lower=br.hit_lower,
                max_deviation_pct=br.max_deviation_pct,
                stale_days=stale_days,
                ok_days=ok_days,
                warning_days=warning_days,
                score=score,
                summary=summary,
            )
        )

    return out


def best_mode_result(results: list[ModeResult]) -> ModeResult | None:
    if not results:
        return None
    return max(results, key=lambda r: r.score)


def _build_mode_summary(
    *,
    mode: str,
    lifetime_days: float,
    hit_upper: bool,
    hit_lower: bool,
    score: float,
) -> str:
    parts = [f"{mode}: score {score:.1f}, lifetime ~{lifetime_days:.1f} d."]
    if hit_lower:
        parts.append("First exit lower.")
    elif hit_upper:
        parts.append("First exit upper.")
    else:
        parts.append("No boundary exit in window.")
    return " ".join(parts)
