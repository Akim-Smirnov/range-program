from range_program.check_all_report import (
    CheckTableRow,
    aggregate_counts,
    format_check_all_table,
    format_summary,
    select_rows,
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


def test_select_rows_filter_and_top_n() -> None:
    rows = [
        CheckTableRow("ETH", "1", "a", "r", "1%", "1%", "1%", "OK"),
        CheckTableRow("BTC", "1", "a", "r", "1%", "1%", "1%", "OUT_OF_RANGE"),
        CheckTableRow("SOL", "1", "a", "r", "1%", "1%", "1%", "WARNING"),
        CheckTableRow("AAA", "—", "—", "—", "—", "—", "x", "ERROR"),
    ]

    problems = select_rows(rows, exclude_ok_by_default=True)
    assert {r.status for r in problems} == {"OUT_OF_RANGE", "WARNING", "ERROR"}

    only_critical = select_rows(rows, statuses={"OUT_OF_RANGE", "ERROR"})
    assert [r.status for r in only_critical] == ["OUT_OF_RANGE", "ERROR"]

    top1 = select_rows(rows, exclude_ok_by_default=True, top_n=1)
    assert len(top1) == 1
    assert top1[0].status == "OUT_OF_RANGE"


def test_format_table_and_summary_smoke() -> None:
    rows = [
        CheckTableRow("BTC", "1", "a", "r", "1%", "1%", "1%", "OUT_OF_RANGE"),
        CheckTableRow("ETH", "1", "a", "r", "1%", "1%", "1%", "OK"),
    ]
    txt = format_check_all_table(rows)
    assert "SYMBOL" in txt and "BTC" in txt
    summ = format_summary(aggregate_counts(rows))
    assert "Summary" in summ and "OK" in summ
