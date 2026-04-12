from dataclasses import replace
from datetime import datetime, timezone

import pytest

from range_program.models.active_range import ActiveRange
from range_program.models.coin import Coin
from range_program.models.recommended_range import RecommendedRange
from range_program.services.evaluator import Evaluator


def _rr(low: float, high: float, center: float) -> RecommendedRange:
    return RecommendedRange(
        low=low,
        high=high,
        center=center,
        width_pct=(high - low) / center * 100 if center else 0.0,
        calculated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        center_method="ema",
        width_method="atr",
    )


def _coin_with_ranges(active: tuple[float, float], rec: tuple[float, float, float]) -> Coin:
    c = Coin.create("TST", mode="balanced")
    ar = ActiveRange(
        low=active[0],
        high=active[1],
        set_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    rr = _rr(rec[0], rec[1], rec[2])
    return replace(c, active_range=ar, recommended_range=rr)


def test_out_of_range_below() -> None:
    c = _coin_with_ranges((100.0, 200.0), (90.0, 210.0, 150.0))
    ev = Evaluator()
    r = ev.evaluate(c, 50.0)
    assert r.status == "OUT_OF_RANGE"


def test_out_of_range_above() -> None:
    c = _coin_with_ranges((100.0, 200.0), (90.0, 210.0, 150.0))
    ev = Evaluator()
    r = ev.evaluate(c, 250.0)
    assert r.status == "OUT_OF_RANGE"


def test_reposition_center_shift() -> None:
    # active center 150, price inside; recommended center far >10%
    c = _coin_with_ranges((100.0, 200.0), (50.0, 250.0, 180.0))
    ev = Evaluator()
    r = ev.evaluate(c, 150.0)
    assert r.status == "REPOSITION"


def test_stale_large_deviation() -> None:
    # active 100-200 center 150; price 175 -> dev ~16.7% > 12%; rec aligned with active to skip REPOSITION
    c = _coin_with_ranges((100.0, 200.0), (100.0, 200.0, 150.0))
    ev = Evaluator()
    r = ev.evaluate(c, 175.0)
    assert r.status == "STALE"


def test_ok_mid() -> None:
    c = _coin_with_ranges((100.0, 200.0), (100.0, 200.0, 150.0))
    ev = Evaluator()
    r = ev.evaluate(c, 150.0)
    assert r.status == "OK"


def test_warning_near_edge_when_stale_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import range_program.services.evaluator as evm

    monkeypatch.setattr(evm, "_STALE_DEVIATION_PCT", 99.0)
    c = _coin_with_ranges((100.0, 200.0), (100.0, 200.0, 150.0))
    r = Evaluator().evaluate(c, 102.0)
    assert r.status == "WARNING"
