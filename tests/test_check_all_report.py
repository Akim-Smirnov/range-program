from range_program.check_all_report import (
    CheckTableRow,
    aggregate_counts,
    status_sort_key,
)


def test_status_sort_order_priority() -> None:
    assert status_sort_key("OUT_OF_RANGE") < status_sort_key("REPOSITION")
    assert status_sort_key("REPOSITION") < status_sort_key("STALE")
    assert status_sort_key("STALE") < status_sort_key("WARNING")
    assert status_sort_key("WARNING") < status_sort_key("OK")
    assert status_sort_key("ERROR") > status_sort_key("OUT_OF_RANGE")


def test_table_rows_sort_by_status_then_symbol() -> None:
    rows = [
        CheckTableRow("ETH", "1", "a", "r", "1%", "1%", "1%", "OK"),
        CheckTableRow("BTC", "1", "a", "r", "1%", "1%", "1%", "OUT_OF_RANGE"),
        CheckTableRow("SOL", "1", "a", "r", "1%", "1%", "1%", "WARNING"),
    ]
    rows.sort(key=lambda r: (r.sort_rank, r.symbol))
    assert [r.symbol for r in rows] == ["BTC", "SOL", "ETH"]


def test_aggregate_counts() -> None:
    rows = [
        CheckTableRow("A", "1", "a", "r", "1%", "1%", "1%", "OK"),
        CheckTableRow("B", "1", "a", "r", "1%", "1%", "1%", "OK"),
        CheckTableRow("C", "—", "—", "—", "—", "—", "x", "ERROR"),
    ]
    c = aggregate_counts(rows)
    assert c["OK"] == 2
    assert c["ERROR"] == 1
